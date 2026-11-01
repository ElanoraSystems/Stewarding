from sqlalchemy import select

from app.models import CorrectiveAction, Notification, TemperatureReading

from .helpers import MGR, STEWARD, loc_id


def fryer(client, h, db):
    made = client.post("/api/equipment/from-template", json={"template": "fryer_oil", "location_id": loc_id(db, "MK"), "name": "Fryer 1"}, headers=h)
    assert made.status_code == 201, made.text
    return made.json()


def daily_form(point, tpm):
    by_stage = {s["stage"]: s for s in point["schedules"]}
    give = {"TPM reading": {"value": tpm}, "Oil temperature": {"value": 175}, "Oil look and smell": {"answer": "Normal"}}
    return [{"schedule_id": by_stage[stage]["id"], **entry} for stage, entry in give.items()]


def record(client, h, point, tpm):
    return client.post("/api/monitoring/readings/batch", json={"equipment_id": point["id"], "readings": daily_form(point, tpm)}, headers=h)


def test_the_frying_oil_template_is_a_short_daily_form_with_the_tpm_limits(client, login, db):
    point = fryer(client, login(MGR), db)
    assert point["kind"] == "Frying oil" and point["code"].startswith("FO-")
    assert [s["stage"] for s in point["schedules"]] == ["TPM reading", "Oil temperature", "Oil look and smell"]  # just what is checked every day
    tpm = point["schedules"][0]
    assert (tpm["unit"], float(tpm["max_value"]), float(tpm["warn_max"])) == ("%", 25.0, 20.0)
    look = point["schedules"][2]
    assert look["fail_options"] == ["Foaming", "Smoking", "Off smell"] and look["required"] is False


def test_a_tpm_reading_from_20_percent_passes_with_an_amber_warning_and_tells_the_supervisor(client, login, db, clock):
    clock.set(2026, 3, 2, 12, 0)  # 16:00 in Dubai, after the 15:00 test time opens
    point = fryer(client, login(MGR), db)
    done = record(client, login(STEWARD), point, 21.5)
    assert done.status_code == 201, done.text
    tpm = next(r for r in done.json() if r["stage"] == "TPM reading")
    assert tpm["passed"] is True and tpm["warning"] is True
    assert all(r["warning"] is False for r in done.json() if r["stage"] != "TPM reading")
    db.expire_all()
    warned = db.scalars(select(Notification).where(Notification.kind == "monitoring_warning")).all()
    assert warned and "Approaching the limit" in warned[0].title
    assert not db.scalars(select(Notification).where(Notification.kind == "monitoring_failed")).all()  # a warning is not a failure


def test_a_low_tpm_reading_has_no_warning_and_one_above_25_fails_with_a_corrective_action(client, login, db, clock):
    clock.set(2026, 3, 2, 12, 0)
    m, steward = login(MGR), login(STEWARD)
    fine = record(client, steward, fryer(client, m, db), 12)
    assert next(r for r in fine.json() if r["stage"] == "TPM reading")["warning"] is False
    bad = record(client, steward, fryer(client, m, db), 26)
    assert bad.status_code == 201
    tpm = next(r for r in bad.json() if r["stage"] == "TPM reading")
    assert tpm["passed"] is False and tpm["warning"] is False
    db.expire_all()
    assert db.scalars(select(CorrectiveAction).where(CorrectiveAction.reading_id == tpm["id"])).first() is not None
    assert db.get(TemperatureReading, tpm["id"]).passed is False


def test_a_warning_level_must_sit_inside_the_limits(client, login, db):
    h = login(MGR)
    point = fryer(client, h, db)
    body = {"stage": "Probe", "parameter": "TPM", "unit": "%", "value_type": "number", "timing": "manual", "min_value": 0, "max_value": 25, "warn_max": 30}
    assert client.post(f"/api/equipment/{point['id']}/schedules", json=body, headers=h).status_code == 422
    ok = client.post(f"/api/equipment/{point['id']}/schedules", json={**body, "warn_max": 20}, headers=h)
    assert ok.status_code == 201 and float(ok.json()["warn_max"]) == 20.0
