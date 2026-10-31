"""Edge cases from the lifecycle of a monitoring reading.

Reading:   recorded -> approved | rejected (rejected: the check is due again)
Failure:   action_required -> retest_due -> resolved | retest_failed ; voided when its reading is rejected
Two step:  time in (open) -> time out (closed)
"""
from datetime import timedelta

from sqlalchemy import select

from app.models import CorrectiveAction, Notification, TemperatureReading
from app.services import alerts

from .helpers import MGR, STEWARD, SUP
from .test_monitoring import mk_stage, record
from .test_two_step_logs import finish, make, start

REASON = "Probe was not in the product"


def reject(client, h, ids, reason=REASON):
    return client.post("/api/monitoring/readings/reject", json={"reading_ids": ids, "reason": reason}, headers=h)


def open_actions(client, h):
    return client.get("/api/monitoring/corrective-actions", headers=h).json()


def test_rejecting_a_failed_reading_closes_its_failure_everywhere(client, login, db, clock):
    steward, sup, m = login(STEWARD), login(SUP), login(MGR)
    eq, wash = mk_stage(client, steward)
    failed = record(client, steward, eq, wash, 40).json()
    assert len(open_actions(client, m)) == 1
    assert reject(client, sup, [failed["id"]]).json() == {"rejected": 1, "skipped": 0}
    assert open_actions(client, m) == []
    action = db.scalar(select(CorrectiveAction).where(CorrectiveAction.reading_id == failed["id"]))
    assert action.status == "voided"
    alert = db.scalar(select(Notification).where(Notification.dedupe_key == f"temp_fail:{failed['id']}"))
    assert alert.resolved_at is not None
    assert client.post(f"/api/monitoring/corrective-actions/{action.id}/action", json={"action": "Fixed the tank"}, headers=steward).status_code == 409
    kpi = client.get("/api/dashboard", headers=m).json()["kpis"]
    assert kpi["failed_checks"] == 0 and kpi["equipment_attention"] == 0
    assert alerts.corrective_alerts(db, clock.now + timedelta(days=2)) == 0


def test_a_rejected_failure_does_not_count_towards_repeated_failures(client, login, db, clock):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    ids = []
    for _ in range(3):
        ids.append(record(client, steward, eq, wash, 40).json()["id"])
        clock.advance(days=1)
    reject(client, sup, ids)
    listing = client.get("/api/equipment", headers=login(MGR)).json()
    assert next(e for e in listing if e["id"] == eq["id"])["needs_attention"] is False


def test_rejecting_a_passing_retest_reopens_the_failure(client, login, db, clock):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    failed = record(client, steward, eq, wash, 40, corrective_action="Refilled the tank").json()
    retest = record(client, steward, eq, wash, 60, retest_of_id=failed["id"]).json()
    action = db.scalar(select(CorrectiveAction).where(CorrectiveAction.reading_id == failed["id"]))
    db.refresh(action)
    assert action.status == "resolved"
    assert reject(client, sup, [retest["id"]]).json()["rejected"] == 1
    db.expire_all()
    assert db.get(CorrectiveAction, action.id).status == "retest_due" and db.get(CorrectiveAction, action.id).resolved_at is None
    again = record(client, steward, eq, wash, 60, retest_of_id=failed["id"])
    assert again.status_code == 201
    db.expire_all()
    assert db.get(CorrectiveAction, action.id).status == "resolved"


def test_rejecting_a_failed_retest_puts_the_original_back_to_retest_due(client, login, db, clock):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    failed = record(client, steward, eq, wash, 40, corrective_action="Refilled the tank").json()
    bad = record(client, steward, eq, wash, 30, retest_of_id=failed["id"]).json()
    action = db.scalar(select(CorrectiveAction).where(CorrectiveAction.reading_id == failed["id"]))
    db.refresh(action)
    assert action.status == "retest_failed"
    reject(client, sup, [bad["id"]])
    db.expire_all()
    assert db.get(CorrectiveAction, action.id).status == "retest_due"
    assert record(client, steward, eq, wash, 60, retest_of_id=failed["id"]).status_code == 201


def test_a_rejected_reading_cannot_be_retested(client, login, db, clock):
    steward, sup = login(STEWARD), login(SUP)
    eq, wash = mk_stage(client, steward)
    failed = record(client, steward, eq, wash, 40, corrective_action="Refilled the tank").json()
    reject(client, sup, [failed["id"]])
    assert record(client, steward, eq, wash, 60, retest_of_id=failed["id"]).status_code == 409


def test_a_rejected_time_in_leaves_the_pending_list_and_cannot_be_closed(client, login, db, clock):
    m, sup = login(MGR), login(SUP)
    point = make(client, m, db, "defrosting")
    started = start(client, m, point).json()
    assert len(client.get("/api/monitoring/pending", headers=m).json()) == 1
    assert reject(client, sup, [started[0]["id"]]).json()["rejected"] == 1
    assert client.get("/api/monitoring/pending", headers=m).json() == []
    assert finish(client, m, point, started[0]["id"]).status_code == 400


def test_a_time_in_with_a_time_out_cannot_be_rejected_alone(client, login, db, clock):
    m, sup = login(MGR), login(SUP)
    point = make(client, m, db, "defrosting")
    started = start(client, m, point).json()
    finish(client, m, point, started[0]["id"])
    assert reject(client, sup, [started[0]["id"]]).json() == {"rejected": 0, "skipped": 1}


def test_an_inactive_point_takes_no_readings(client, login, db, clock):
    m, steward = login(MGR), login(STEWARD)
    eq, wash = mk_stage(client, steward)
    client.put(f"/api/equipment/{eq['id']}", json={"active": False}, headers=m)
    assert record(client, steward, eq, wash, 60).status_code == 400


def test_a_time_out_that_stays_missing_raises_one_alert(client, login, db, clock):
    m = login(MGR)
    point = make(client, m, db, "defrosting")
    start(client, m, point)
    assert alerts.pending_time_outs(db, clock.now + timedelta(hours=13)) == 0   # the defrosting check allows 24 hours
    assert alerts.pending_time_outs(db, clock.now + timedelta(hours=25)) > 0
    assert alerts.pending_time_outs(db, clock.now + timedelta(hours=26)) == 0
    assert db.scalar(select(Notification).where(Notification.kind == "time_out_missing")) is not None
