from sqlalchemy import select

from app.models import Notification

from .helpers import MGR, STEWARD, SUP, loc_id
from .test_alerts import notes, run


def make(client, h, db, code="TH-MK-1", **over):
    return client.post("/api/calibration/probes", json={"code": code, "name": "Probe one", "location_id": loc_id(db, "MK"), **over}, headers=h)


def calibrate(client, h, probe, reading=0.2, method="ice_point", **over):
    return client.post(f"/api/calibration/probes/{probe['id']}/calibrations", json={"method": method, "reading_c": reading, **over}, headers=h)


def state(client, h, probe_id):
    return next(p for p in client.get("/api/calibration/probes", headers=h).json() if p["id"] == probe_id)


def test_only_a_manager_adds_probes_and_codes_are_unique(client, login, db):
    assert make(client, login(MGR), db).status_code == 201
    assert make(client, login(MGR), db).status_code == 409
    assert make(client, login(MGR), db, code="th-mk-1").status_code == 409  # same code in another case
    for who in (SUP, STEWARD):
        assert make(client, login(who), db, code="TH-MK-2").status_code == 403


def test_a_probe_is_never_ok_until_checked_then_due_soon_then_overdue(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)
    probe = make(client, login(MGR), db).json()
    assert probe["status"] == "never"
    sup = login(SUP)
    done = calibrate(client, sup, probe, reading=0.4).json()
    assert done["status"] == "ok" and done["last"]["passed"] is True and done["last"]["by"]
    clock.advance(days=28)
    assert state(client, sup, probe["id"])["status"] == "due_soon"
    clock.advance(days=3)
    assert state(client, sup, probe["id"])["status"] == "overdue"
    assert calibrate(client, sup, probe, reading=0.1).json()["status"] == "ok"  # checked again


def test_a_probe_out_by_more_than_a_degree_fails_needs_a_note_and_raises_an_alert(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)
    probe = make(client, login(MGR), db).json()
    sup = login(SUP)
    assert calibrate(client, sup, probe, reading=2.5).status_code == 400  # what was done about it?
    failed = calibrate(client, sup, probe, reading=2.5, comment="Taken out of use, new probe ordered")
    assert failed.status_code == 201 and failed.json()["status"] == "failed" and failed.json()["last"]["passed"] is False
    alert = db.scalar(select(Notification).where(Notification.kind == "probe_failed"))
    assert alert.priority == "critical" and alert.requires_ack and "2.5" in alert.body
    assert calibrate(client, sup, probe, reading=0.0).json()["status"] == "ok"  # a good check puts it back in use


def test_the_reference_for_other_checks_is_required_and_boiling_is_100(client, login, db):
    probe = make(client, login(MGR), db).json()
    sup = login(SUP)
    assert calibrate(client, sup, probe, reading=70, method="reference").status_code == 422
    other = calibrate(client, sup, probe, reading=70.5, method="reference", reference_c=70).json()
    assert other["status"] == "ok" and float(other["last"]["reference_c"]) == 70
    assert float(calibrate(client, sup, probe, reading=99.4, method="boiling_point").json()["last"]["reference_c"]) == 100
    history = client.get(f"/api/calibration/probes/{probe['id']}/calibrations", headers=sup).json()
    assert len(history) == 2 and history[0]["deviation"] is not None


def test_reminders_go_to_supervisors_once_per_cycle_and_close_when_checked(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)
    probe = make(client, login(MGR), db).json()
    run(db, clock)
    never = notes(db, "probe_never")
    assert never and all(n.priority == "high" for n in never)
    count = len(never)
    run(db, clock)
    assert len(notes(db, "probe_never")) == count  # not repeated
    calibrate(client, login(SUP), probe, reading=0.0)
    assert all(n.resolved_at for n in notes(db, "probe_never"))
    clock.advance(days=31)
    run(db, clock)
    assert notes(db, "probe_overdue")


def test_the_calibration_record_lists_checks_and_tints_failures(client, login, db, clock):
    clock.set(2026, 3, 2, 8, 0)
    probe = make(client, login(MGR), db).json()
    sup = login(SUP)
    calibrate(client, sup, probe, reading=0.2)
    calibrate(client, sup, probe, reading=3.0, comment="Replaced the probe")
    url = "/api/reports/records/calibration?date_from=2026-03-02&date_to=2026-03-02"
    doc = client.get(url, headers=login(MGR)).json()
    group = next(g for g in doc["groups"] if "Probe calibration" in g["title"] and g["rows"])
    assert [r["result"] for r in group["rows"]] == ["Passed", "Failed"]
    assert group["rows"][1]["_tone"] == {"result": "bad"} and group["rows"][1]["deviation"] == "+3.00 °C"
    only = client.get(url + "&status=failed", headers=login(MGR)).json()
    assert [r["result"] for g in only["groups"] for r in g["rows"]] == ["Failed"]
