from sqlalchemy import select

from app.models import CorrectiveAction, Notification, User
from app.scheduler import run_cycle
from app.services.alerts import run_alerts

from .helpers import MGR, STEWARD, SUP, loc_id


def run(db, clock):
    totals = run_alerts(db, clock.now)
    db.commit()
    return totals


def notes(db, kind):
    db.expire_all()
    return db.scalars(select(Notification).where(Notification.kind == kind)).all()


def emails(db, rows):
    return {db.get(User, n.user_id).email for n in rows}


def generate(client, login, db, code="MK"):
    client.post("/api/checklists/generate", json={"location_id": loc_id(db, code)}, headers=login(MGR))


def test_missing_checkin_alert_waits_for_grace_then_fires_once(client, login, db, clock):
    run(db, clock)  # 06:05, inside the 10 minute grace window
    assert notes(db, "no_checkin") == []
    clock.set(2026, 3, 2, 2, 30)
    run(db, clock)
    first = notes(db, "no_checkin")
    assert first and emails(db, first) >= {"manager@example.test", "sup.mk@example.test", "steward.mk@example.test"}
    run(db, clock)
    assert len(notes(db, "no_checkin")) == len(first)


def test_no_alert_for_someone_who_checked_in_or_after_the_shift(client, login, db, clock):
    client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "MK")}, headers=login(STEWARD))
    clock.set(2026, 3, 2, 2, 30)
    run(db, clock)
    titles = [n.title for n in notes(db, "no_checkin")]
    assert not any("Sid Steward" in t for t in titles)
    run(db, clock)
    mk = loc_id(db, "MK")
    before = len([n for n in notes(db, "no_checkin") if n.location_id == mk])
    clock.set(2026, 3, 2, 12, 0)  # 16:00 Dubai, the morning shift ended at 14:00 (London is still mid-shift)
    run(db, clock)
    assert len([n for n in notes(db, "no_checkin") if n.location_id == mk]) == before


def test_forgotten_checkout_alerts_employee_and_supervisors(client, login, db, clock):
    client.post("/api/attendance/check-in", json={"location_id": loc_id(db, "MK")}, headers=login(STEWARD))
    clock.advance(hours=17)
    run(db, clock)
    alert = notes(db, "missed_checkout")
    assert emails(db, alert) == {"manager@example.test", "sup.mk@example.test", "steward.mk@example.test"}
    run(db, clock)
    assert len(notes(db, "missed_checkout")) == len(alert)


def test_checklist_reminder_overdue_and_escalation_timeline(client, login, db, clock):
    generate(client, login, db)
    clock.set(2026, 3, 2, 8, 0)  # 12:00 Dubai, deadline 13:30
    run(db, clock)
    assert notes(db, "task_due_soon") == []
    clock.set(2026, 3, 2, 9, 5)  # inside the 30 minute lead window
    run(db, clock)
    soon = notes(db, "task_due_soon")
    assert emails(db, soon) == {"steward.mk@example.test", "sup.mk@example.test"}
    assert "14 task(s) due at 13:30" in soon[0].title
    assert notes(db, "task_overdue") == []
    clock.set(2026, 3, 2, 9, 31)
    run(db, clock)
    overdue = notes(db, "task_overdue")
    assert overdue and overdue[0].priority == "high" and "overdue since 13:30" in overdue[0].title
    assert notes(db, "task_escalated") == []
    clock.set(2026, 3, 2, 10, 1)  # 31 minutes late: escalate to supervisor
    run(db, clock)
    assert emails(db, notes(db, "task_escalated")) == {"sup.mk@example.test"}
    clock.set(2026, 3, 2, 11, 31)  # 121 minutes late: escalate to manager
    run(db, clock)
    manager = [n for n in notes(db, "task_escalated") if n.priority == "critical"]
    assert emails(db, manager) == {"manager@example.test"} and manager[0].requires_ack
    count = len(db.scalars(select(Notification)).all())
    run(db, clock)
    assert len(db.scalars(select(Notification)).all()) == count


def test_reminder_lead_time_is_configurable(client, login, db, clock):
    generate(client, login, db)
    assert client.put("/api/settings", json={"values": {"reminder.lead_minutes": 60}}, headers=login(MGR)).status_code == 200
    clock.set(2026, 3, 2, 8, 35)  # 55 minutes before the deadline
    run(db, clock)
    assert notes(db, "task_due_soon")


def test_assigned_employee_gets_a_personal_overdue_alert(client, login, db, clock):
    generate(client, login, db)
    emps = {e["employee_code"]: e["id"] for e in client.get("/api/employees?size=50", headers=login(MGR)).json()["items"]}
    tasks = client.get("/api/checklists/instances?size=200", headers=login(SUP)).json()["items"]
    task = next(t for t in tasks if "Clean drains" in t["description"])
    client.post(f"/api/checklists/instances/{task['id']}/assign", json={"employee_id": emps["E004"]}, headers=login(SUP))
    clock.set(2026, 3, 2, 9, 40)
    run(db, clock)
    mine = [n for n in notes(db, "task_overdue") if n.title.startswith("Your task is overdue")]
    assert [db.get(User, n.user_id).email for n in mine] == ["steward.mk@example.test"]


def test_task_level_escalation_minutes(client, login, db, clock):
    m = login(MGR)
    tpl = client.post("/api/checklists/templates", headers=m, json={
        "name": "Safety", "category": "Safety", "location_id": loc_id(db, "MK"), "frequency": "daily"}).json()
    client.post(f"/api/checklists/templates/{tpl['id']}/tasks", headers=m, json={
        "description": "Check gas shut-off", "deadline_time": "12:00:00", "escalation_minutes": 10})
    generate(client, login, db)
    clock.set(2026, 3, 2, 8, 5)  # 5 minutes after the 12:00 deadline
    run(db, clock)
    assert not [n for n in notes(db, "task_escalated") if "gas shut-off" in n.title]
    clock.set(2026, 3, 2, 8, 11)
    run(db, clock)
    assert [n for n in notes(db, "task_escalated") if "gas shut-off" in n.title]


def test_completed_tasks_do_not_raise_alerts(client, login, db, clock):
    generate(client, login, db)
    for t in client.get("/api/checklists/instances?size=200", headers=login(SUP)).json()["items"]:
        if t["frequency"] != "weekly":
            client.post(f"/api/checklists/instances/{t['id']}/complete", json={}, headers=login(SUP))
    clock.set(2026, 3, 2, 9, 40)
    run(db, clock)
    assert notes(db, "task_overdue") == []


def test_monitoring_due_then_overdue_alerts(client, login, db, clock):
    run(db, clock)  # 06:05, wash check is due
    due = notes(db, "monitoring_due")
    assert due and emails(db, due) >= {"steward.mk@example.test", "sup.mk@example.test"}
    assert notes(db, "monitoring_overdue") == []
    clock.advance(minutes=40)  # past the 30 minute grace
    run(db, clock)
    over = notes(db, "monitoring_overdue")
    assert over and all(n.requires_ack and n.priority == "high" for n in over)
    assert emails(db, over) == {"manager@example.test", "sup.mk@example.test"}
    count = len(notes(db, "monitoring_overdue"))
    run(db, clock)
    assert len(notes(db, "monitoring_overdue")) == count


def test_retest_overdue_and_escalation_to_manager(client, login, db, clock):
    h = login(STEWARD)
    eq = next(e for e in client.get("/api/monitoring/equipment", headers=h).json() if e["code"] == "DW-MK-1")
    sched = next(s for s in eq["schedules"] if s["stage"] == "wash")
    failed = client.post("/api/monitoring/readings", headers=h, json={
        "equipment_id": eq["id"], "schedule_id": sched["id"], "value": 40, "corrective_action": "Refilled the tank"}).json()
    clock.advance(minutes=20)
    run(db, clock)
    retest = notes(db, "retest_due")
    assert retest and all(n.priority == "critical" and n.requires_ack for n in retest)
    assert notes(db, "monitoring_escalated") == []
    clock.advance(minutes=45)  # 65 minutes since the failed reading
    run(db, clock)
    escalated = notes(db, "monitoring_escalated")
    assert emails(db, escalated) == {"manager@example.test"}
    assert db.get(CorrectiveAction, failed["corrective_action"]["id"]).escalated_at is not None
    count = len(notes(db, "monitoring_escalated"))
    run(db, clock)
    assert len(notes(db, "monitoring_escalated")) == count


def test_low_stock_recheck_notifies_the_right_location_once_a_day(client, login, db, clock):
    run(db, clock)
    low = notes(db, "low_stock")
    rb = [n for n in low if n.location_id == loc_id(db, "RB")]
    assert rb and emails(db, rb) == {"manager@example.test", "sup.rb@example.test"}
    assert "sup.mk@example.test" not in emails(db, rb)
    run(db, clock)
    assert len(notes(db, "low_stock")) == len(low)
    clock.advance(days=1)
    run(db, clock)
    assert len(notes(db, "low_stock")) > len(low)


def test_daily_summary_is_sent_after_eight_local_once_per_day(client, login, db, clock):
    clock.set(2026, 3, 2, 3, 0)  # 07:00 Dubai
    run(db, clock)
    assert [n for n in notes(db, "daily_summary") if n.location_id == loc_id(db, "MK")] == []
    clock.set(2026, 3, 2, 4, 30)  # 08:30 Dubai, a temperature check is overdue
    run(db, clock)
    mk = [n for n in notes(db, "daily_summary") if n.location_id == loc_id(db, "MK")]
    assert mk and emails(db, mk) == {"manager@example.test", "sup.mk@example.test"}
    assert "critical" in mk[0].title
    run(db, clock)
    assert len([n for n in notes(db, "daily_summary") if n.location_id == loc_id(db, "MK")]) == len(mk)


def test_scheduler_cycle_is_idempotent_and_includes_alerts(client, login, db, clock):
    clock.set(2026, 3, 2, 9, 40)
    first = run_cycle(db, clock.now)
    assert first["created"] > 0 and "alerts" in first
    count = len(db.scalars(select(Notification)).all())
    second = run_cycle(db, clock.now)
    assert second["created"] == 0
    assert len(db.scalars(select(Notification)).all()) == count


def test_other_locations_are_not_alerted_for_mk_tasks(client, login, db, clock):
    generate(client, login, db)
    clock.set(2026, 3, 2, 9, 40)
    run(db, clock)
    recipients_ = emails(db, [n for n in notes(db, "task_overdue") if n.location_id == loc_id(db, "MK")])
    assert recipients_ and not {"sup.rb@example.test", "steward.rb@example.test"} & recipients_
