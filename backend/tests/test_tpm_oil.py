from sqlalchemy import select

from app.models import CorrectiveAction, Notification, TemperatureReading

from .helpers import MGR, STEWARD, loc_id


def fryer(client, h, db):
    made = client.post("/api/equipment/from-template", json={"template": "fryer_oil", "location_id": loc_id(db, "MK"), "name": "Fryer 1"}, headers=h)
    assert made.status_code == 201, made.text
    return made.json()


def lunch_form(point, tpm):
    by_stage = {s["stage"]: s for s in point["schedules"] if s["stage"].endswith("(lunch)")}
    give = {"TPM reading (lunch)": {"value": tpm}, "Oil temperature at test (lunch)": {"value": 175}, "Oil type or batch (lunch)": {"answer": "Sunflower B-204"},
            "Date oil last changed (lunch)": {"answer": "2026-02-28"}, "Oil look and smell (lunch)": {"answer": "Normal"}, "Oil filtered today (lunch)": {"value": 1}}
    return [{"schedule_id": by_stage[stage]["id"], **entry} for stage, entry in give.items()]


def record(client, h, point, tpm):
    return client.post("/api/monitoring/readings/batch", json={"equipment_id": point["id"], "readings": lunch_form(point, tpm)}, headers=h)


def test_the_frying_oil_template_has_a_form_for_lunch_and_dinner_with_the_tpm_limits(client, login, db):
    point = fryer(client, login(MGR), db)
    assert point["kind"] == "Frying oil" and point["code"].startswith("FO-")
    assert len(point["schedules"]) == 16
    tpm = next(s for s in point["schedules"] if s["stage"] == "TPM reading (dinner)")
    assert (tpm["unit"], float(tpm["max_value"]), float(tpm["warn_max"])) == ("%", 25.0, 20.0) and str(tpm["time_of_day"])[:5] == "23:00"
    look = next(s for s in point["schedules"] if s["stage"] == "Oil look and smell (lunch)")
    assert look["fail_options"] == ["Foaming", "Smoking", "Off smell"]
    assert all(not s["required"] for s in point["schedules"] if s["parameter"] in ("Photo", "Meter"))


def test_a_tpm_reading_from_20_percent_passes_with_an_amber_warning_and_tells_the_supervisor(client, login, db, clock):
    clock.set(2026, 3, 2, 12, 0)  # 16:00 in Dubai, after lunch service
    point = fryer(client, login(MGR), db)
    done = record(client, login(STEWARD), point, 21.5)
    assert done.status_code == 201, done.text
    tpm = next(r for r in done.json() if r["stage"] == "TPM reading (lunch)")
    assert tpm["passed"] is True and tpm["warning"] is True
    assert all(r["warning"] is False for r in done.json() if r["stage"] != "TPM reading (lunch)")
    db.expire_all()
    warned = db.scalars(select(Notification).where(Notification.kind == "monitoring_warning")).all()
    assert warned and "Approaching the limit" in warned[0].title
    assert not db.scalars(select(Notification).where(Notification.kind == "monitoring_failed")).all()  # a warning is not a failure


def test_a_low_tpm_reading_has_no_warning_and_one_above_25_fails_with_a_corrective_action(client, login, db, clock):
    clock.set(2026, 3, 2, 12, 0)
    m, steward = login(MGR), login(STEWARD)
    fine = record(client, steward, fryer(client, m, db), 12)
    assert next(r for r in fine.json() if r["stage"] == "TPM reading (lunch)")["warning"] is False
    bad = record(client, steward, fryer(client, m, db), 26)
    assert bad.status_code == 201
    tpm = next(r for r in bad.json() if r["stage"] == "TPM reading (lunch)")
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
