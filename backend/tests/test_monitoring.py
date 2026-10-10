from decimal import Decimal

from sqlalchemy import select

from app.models import ApprovalRecord, AuditLog, CorrectiveAction, Location, Notification, TemperatureReading

MGR = "manager@example.test"
SUP = "sup.mk@example.test"
STEWARD = "steward.mk@example.test"


def mk_stage(client, h, stage="wash", equipment_code="DW-MK-1"):
    items = client.get("/api/monitoring/equipment", headers=h).json()
    eq = next(e for e in items if e["code"] == equipment_code)
    return eq, next(s for s in eq["schedules"] if s["stage"] == stage)


def record(client, h, eq, sched, temp, **extra):
    body = {"equipment_id": eq["id"], "schedule_id": sched["id"], "value": temp, **extra}
    return client.post("/api/monitoring/readings", json=body, headers=h)


def test_passing_reading_snapshots_limits(client, login, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    r = record(client, h, eq, sched, 60.0)
    assert r.status_code == 201
    body = r.json()
    assert body["passed"] is True and body["min_limit"] == 55.0 and body["max_limit"] == 65.0
    assert body["corrective_action"] is None


def test_out_of_range_reading_is_kept_and_opens_corrective_action(client, login, db, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    body = record(client, h, eq, sched, 48.5).json()
    assert body["passed"] is False and body["corrective_action"]["status"] == "action_required"
    assert db.scalar(select(TemperatureReading.passed).where(TemperatureReading.id == body["id"])) is False
    alert = db.scalar(select(Notification).where(Notification.kind == "monitoring_failed"))
    assert alert.priority == "critical" and alert.requires_ack and alert.resolved_at is None


def test_limit_boundaries_are_inclusive(client, login, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    assert record(client, h, eq, sched, 55.0).json()["passed"] is True
    assert record(client, h, eq, sched, 65.0).json()["passed"] is True
    assert record(client, h, eq, sched, 65.1).json()["passed"] is False
    assert record(client, h, eq, sched, 54.9).json()["passed"] is False


def test_supervisors_and_manager_are_alerted_but_not_other_locations(client, login, db, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    record(client, h, eq, sched, 40)
    users = {n.user_id for n in db.scalars(select(Notification).where(Notification.kind == "monitoring_failed"))}
    from app.models import User
    emails = {db.get(User, u).email for u in users}
    assert emails == {"manager@example.test", "sup.mk@example.test"}


def test_corrective_action_then_retest_resolves_and_keeps_both_readings(client, login, db, clock):
    h, sup = login(STEWARD), login(SUP)
    eq, sched = mk_stage(client, h)
    failed = record(client, h, eq, sched, 45).json()
    early = record(client, h, eq, sched, 60, retest_of_id=failed["id"])
    assert early.status_code == 409  # corrective action not recorded yet
    action = failed["corrective_action"]
    assert client.post(f"/api/monitoring/corrective-actions/{action['id']}/action", json={"action": "x"}, headers=h).status_code == 422
    done = client.post(f"/api/monitoring/corrective-actions/{action['id']}/action",
                       json={"action": "Descaled the wash tank and refilled"}, headers=h).json()
    assert done["status"] == "retest_due" and done["retest_due_at"]
    clock.advance(minutes=20)
    retest = record(client, h, eq, sched, 61, retest_of_id=failed["id"])
    assert retest.status_code == 201 and retest.json()["passed"] is True
    assert db.get(CorrectiveAction, action["id"]).status == "resolved"
    assert db.scalar(select(Notification.resolved_at).where(Notification.kind == "monitoring_failed")) is not None
    assert db.scalar(select(TemperatureReading.id).where(TemperatureReading.id == failed["id"]))
    assert record(client, sup, eq, sched, 61, retest_of_id=failed["id"]).status_code == 409  # already retested


def test_failed_retest_opens_a_new_action_without_touching_the_first_reading(client, login, db, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    first = record(client, h, eq, sched, 45, corrective_action="Checked heater element").json()
    assert first["corrective_action"]["status"] == "retest_due"
    second = record(client, h, eq, sched, 46, retest_of_id=first["id"]).json()
    assert second["passed"] is False and second["corrective_action"]["status"] == "action_required"
    assert db.get(CorrectiveAction, first["corrective_action"]["id"]).status == "retest_failed"
    assert db.get(TemperatureReading, first["id"]).value == 45


def test_retest_must_reference_failed_reading_of_same_stage(client, login, clock):
    h = login(STEWARD)
    eq, wash = mk_stage(client, h)
    _, rinse = mk_stage(client, h, "final_rinse")
    ok = record(client, h, eq, wash, 60).json()
    assert record(client, h, eq, wash, 60, retest_of_id=ok["id"]).status_code == 400
    failed = record(client, h, eq, wash, 40, corrective_action="Refilled tank").json()
    assert record(client, h, eq, rinse, 85, retest_of_id=failed["id"]).status_code == 400


def test_changing_limits_does_not_rewrite_history(client, login, clock):
    m = login(MGR)
    eq, sched = mk_stage(client, m)
    old = record(client, m, eq, sched, 70).json()
    assert old["passed"] is False
    body = {"stage": "wash", "timing": "startup", "time_of_day": "06:00:00", "min_value": 50, "max_value": 75}
    assert client.put(f"/api/equipment/schedules/{sched['id']}", json=body, headers=m).status_code == 200
    readings = client.get("/api/monitoring/readings", headers=m).json()["items"]
    assert readings[0]["passed"] is False and readings[0]["max_limit"] == 65.0
    assert record(client, m, eq, sched, 70).json()["passed"] is True


def test_only_manager_can_change_limits_and_it_is_audited(client, login, db, clock):
    eq, sched = mk_stage(client, login(MGR))
    body = {"stage": "wash", "timing": "startup", "min_value": 10, "max_value": 99}
    for email in (STEWARD, SUP):
        assert client.put(f"/api/equipment/schedules/{sched['id']}", json=body, headers=login(email)).status_code == 403
        assert client.post(f"/api/equipment/{eq['id']}/schedules", json=body, headers=login(email)).status_code == 403
    assert client.put(f"/api/equipment/schedules/{sched['id']}", json=body, headers=login(MGR)).status_code == 200
    log = db.scalar(select(AuditLog).where(AuditLog.action == "equipment.schedule_update"))
    assert Decimal(log.before["min_value"]) == 55 and Decimal(log.after["min_value"]) == 10


def test_invalid_limits_are_rejected(client, login, clock):
    eq, _ = mk_stage(client, login(MGR))
    m = login(MGR)
    base = {"stage": "wash", "timing": "startup"}
    assert client.post(f"/api/equipment/{eq['id']}/schedules", json={**base, "min_value": 70, "max_value": 60}, headers=m).status_code == 422
    assert client.post(f"/api/equipment/{eq['id']}/schedules", json=base, headers=m).status_code == 422
    assert client.post(f"/api/equipment/{eq['id']}/schedules", json={**base, "timing": "interval", "min_value": 1}, headers=m).status_code == 422


def test_cross_location_recording_is_blocked(client, login, db, clock):
    eq, sched = mk_stage(client, login(MGR))
    assert record(client, login("steward.rb@example.test"), eq, sched, 60).status_code == 403
    assert record(client, login("sup.rb@example.test"), eq, sched, 60).status_code == 403
    listing = client.get("/api/monitoring/equipment", headers=login("steward.rb@example.test")).json()
    assert {e["code"] for e in listing} == {"GW-RB-1"}


def test_stage_without_limits_cannot_be_recorded(client, login, db, clock):
    from app.models import EquipmentSchedule

    eq, sched = mk_stage(client, login(MGR))
    row_ = db.get(EquipmentSchedule, sched["id"])
    row_.min_value = row_.max_value = None
    db.commit()
    assert record(client, login(STEWARD), eq, sched, 60).status_code == 400


def test_due_checks_move_from_due_to_done_and_overdue(client, login, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)

    def statuses():
        return {(d["schedule_id"], d["slot_at"][11:16]): d["status"]
                for d in client.get("/api/monitoring/due", headers=h).json() if d["equipment_id"] == eq["id"]}

    s = statuses()
    assert s[(sched["id"], "02:00")] == "due"  # 06:00 Dubai
    record(client, h, eq, sched, 60)
    assert statuses()[(sched["id"], "02:00")] == "done"
    clock.advance(hours=4, minutes=20)  # 10:25 Dubai

    def rinse(slot_utc):
        return next(d["status"] for d in client.get("/api/monitoring/due", headers=h).json()
                    if d["stage"] == "final_rinse" and d["slot_at"][11:16] == slot_utc and d["equipment_id"] == eq["id"])

    assert rinse("02:00") == "overdue"   # 06:00 slot never recorded
    assert rinse("06:00") == "due"       # 10:00 slot is inside its 30 minute grace window
    assert rinse("10:00") == "upcoming"  # 14:00 slot


def test_review_rules(client, login, clock):
    h, sup = login(STEWARD), login(SUP)
    eq, sched = mk_stage(client, h)
    reading = record(client, h, eq, sched, 60).json()
    url = f"/api/monitoring/readings/{reading['id']}/review"
    assert client.post(url, headers=h).status_code == 403
    own = record(client, sup, eq, sched, 60).json()
    assert client.post(f"/api/monitoring/readings/{own['id']}/review", headers=sup).status_code == 403
    assert client.post(url, headers=sup).json()["reviewed_by"]
    assert client.post(url, headers=sup).status_code == 409


def test_manager_decision_on_corrective_action(client, login, db, clock):
    h, m = login(STEWARD), login(MGR)
    eq, sched = mk_stage(client, h)
    failed = record(client, h, eq, sched, 40, corrective_action="Reset the thermostat").json()
    url = f"/api/monitoring/corrective-actions/{failed['corrective_action']['id']}/decision"
    assert client.post(url, json={"decision": "approve"}, headers=h).status_code == 403
    assert client.post(url, json={"decision": "reject"}, headers=m).status_code == 400
    rejected = client.post(url, json={"decision": "reject", "note": "Not enough detail"}, headers=m)
    assert rejected.json()["status"] == "action_required"
    assert db.scalar(select(Notification.id).where(Notification.kind == "corrective_action_rejected"))
    approved = client.post(url, json={"decision": "approve", "note": "Verified on site"}, headers=m)
    assert approved.json()["status"] == "resolved"
    assert len(db.scalars(select(ApprovalRecord)).all()) == 2
    assert client.post(url, json={"decision": "approve"}, headers=m).status_code == 409


def test_repeated_failures_raise_a_maintenance_alert_once_per_day(client, login, db, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    for _ in range(4):
        record(client, h, eq, sched, 30)
    alerts = db.scalars(select(Notification).where(Notification.kind == "equipment_maintenance")).all()
    assert alerts and len({(a.user_id, a.dedupe_key) for a in alerts}) == len(alerts)
    listing = client.get("/api/equipment", headers=login(MGR)).json()
    assert next(e for e in listing if e["id"] == eq["id"])["needs_attention"] is True


def test_corrective_actions_list_is_location_scoped(client, login, db, clock):
    h = login(STEWARD)
    eq, sched = mk_stage(client, h)
    record(client, h, eq, sched, 30)
    assert len(client.get("/api/monitoring/corrective-actions", headers=login(SUP)).json()) == 1
    assert client.get("/api/monitoring/corrective-actions", headers=login("sup.rb@example.test")).json() == []
