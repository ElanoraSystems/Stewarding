from datetime import date, datetime

from sqlalchemy import select

from app.models import AuditLog, ChecklistInstance, Location, Notification
from app.scheduler import run_cycle
from app.services import starter

MGR = "manager@example.test"
STEWARD = "steward.mk@example.test"
SUP = "sup.mk@example.test"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def loc_id(db, code):
    return db.scalar(select(Location.id).where(Location.code == code))


def generate(client, login, db, code="MK"):
    r = client.post("/api/checklists/generate", json={"location_id": loc_id(db, code)}, headers=login(MGR))
    assert r.status_code == 200
    return r.json()["created"]


def instances(client, h, **params):
    query = "&".join(f"{k}={v}" for k, v in {"size": 200, **params}.items())
    return client.get(f"/api/checklists/instances?{query}", headers=h).json()["items"]


def find(client, h, text):
    return next(i for i in instances(client, h) if text in i["description"])


def test_generation_is_idempotent_and_follows_weekdays(client, login, db, clock):
    first = generate(client, login, db)
    assert first == len(starter.DAILY) + len(starter.WEEKLY)  # Monday: daily plus Monday-only weekly tasks
    assert generate(client, login, db) == 0
    clock.set(2026, 3, 3, 2, 5)  # Tuesday
    assert generate(client, login, db) == len(starter.DAILY)


def test_yesterdays_completion_does_not_count_today(client, login, db, clock):
    generate(client, login, db)
    h = login(STEWARD)
    task = find(client, h, "Clean drains")
    assert client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=h).status_code == 200
    clock.set(2026, 3, 3, 2, 5)
    generate(client, login, db)
    today = [i for i in instances(client, h, day="2026-03-03") if i["task_id"] == task["task_id"]]
    assert len(today) == 1 and today[0]["status"] == "not_started" and today[0]["id"] != task["id"]


def test_scheduler_run_creates_for_every_location_and_marks_overdue(client, login, db, clock):
    result = run_cycle(db, clock.now)
    assert result["created"] > 0 and result["overdue"] == 0
    assert run_cycle(db, clock.now)["created"] == 0
    clock.set(2026, 3, 2, 10, 0)  # 14:00 Dubai, after the 13:30 daily deadline
    assert run_cycle(db, clock.now)["overdue"] > 0
    overdue = instances(client, login(MGR), status="overdue", location_id=loc_id(db, "MK"))
    assert overdue and all(i["effective_status"] == "overdue" for i in overdue)


def test_overdue_is_computed_even_before_scheduler_runs_and_future_is_excluded(client, login, db, clock):
    generate(client, login, db)
    clock.set(2026, 3, 2, 10, 0)
    h = login(MGR)
    assert instances(client, h, status="overdue")
    assert not [i for i in instances(client, h) if i["frequency"] == "weekly" and i["effective_status"] == "overdue"]
    not_started = instances(client, h, status="not_started")
    assert all(i["frequency"] == "weekly" for i in not_started)


def test_steward_sees_only_own_location_and_steward_tasks(client, login, db, clock):
    generate(client, login, db)
    generate(client, login, db, "BQ")
    items = instances(client, login(STEWARD))
    assert items and {i["location_id"] for i in items} == {loc_id(db, "MK")}
    assert not [i for i in items if "weekly supervisor inspection" in i["description"]]
    manager_items = instances(client, login(MGR))
    assert {i["location_id"] for i in manager_items} >= {loc_id(db, "MK"), loc_id(db, "BQ")}


def test_verification_flow_blocks_self_approval(client, login, db, clock):
    generate(client, login, db)
    steward, sup = login(STEWARD), login(SUP)
    task = find(client, steward, "Clean dishwasher filters")
    done = client.post(f"/api/checklists/instances/{task['id']}/complete", json={"comment": "done"}, headers=steward)
    assert done.json()["status"] == "pending_verification"
    assert client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": True}, headers=steward).status_code == 403
    assert client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": False}, headers=sup).status_code == 400
    ok = client.post(f"/api/checklists/instances/{task['id']}/verify", json={"approve": True}, headers=sup)
    assert ok.json()["status"] == "verified" and ok.json()["verified_by"]
    assert db.scalar(select(Notification.id).where(Notification.kind == "verification_needed"))


def test_supervisor_cannot_verify_own_work_and_rejection_reopens(client, login, db, clock):
    generate(client, login, db)
    sup, steward = login(SUP), login(STEWARD)
    own = find(client, sup, "Clean glasswasher filters")
    client.post(f"/api/checklists/instances/{own['id']}/complete", json={}, headers=sup)
    assert client.post(f"/api/checklists/instances/{own['id']}/verify", json={"approve": True}, headers=sup).status_code == 403
    other = find(client, steward, "Clean dishwasher filters")
    client.post(f"/api/checklists/instances/{other['id']}/complete", json={}, headers=steward)
    rejected = client.post(f"/api/checklists/instances/{other['id']}/verify",
                           json={"approve": False, "comment": "Filter still dirty"}, headers=sup)
    assert rejected.json()["status"] == "failed"
    again = client.post(f"/api/checklists/instances/{other['id']}/complete", json={}, headers=steward)
    assert again.status_code == 200 and again.json()["status"] == "pending_verification"


def test_completed_task_cannot_be_completed_twice(client, login, db, clock):
    generate(client, login, db)
    h = login(STEWARD)
    task = find(client, h, "Separate and remove waste")
    assert client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=h).status_code == 200
    assert client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=h).status_code == 409


def test_future_dated_task_cannot_be_completed(client, login, db, clock):
    generate(client, login, db)
    task = find(client, login(STEWARD), "Clean drains")
    inst = db.get(ChecklistInstance, task["id"])
    inst.local_date = date(2026, 3, 9)
    db.commit()
    r = client.post(f"/api/checklists/instances/{task['id']}/complete", json={}, headers=login(STEWARD))
    assert r.status_code == 400


def test_reading_and_photo_evidence_are_enforced(client, login, db, clock):
    m = login(MGR)
    tpl = client.post("/api/checklists/templates", headers=m, json={
        "name": "Chemical check", "category": "Safety", "location_id": loc_id(db, "MK"), "frequency": "daily"}).json()
    client.post(f"/api/checklists/templates/{tpl['id']}/tasks", headers=m, json={
        "description": "Record sanitizer strength", "requires_reading": True, "requires_photo": True,
        "deadline_time": "12:00:00"})
    generate(client, login, db)
    h = login(STEWARD)
    task = find(client, h, "sanitizer strength")
    url = f"/api/checklists/instances/{task['id']}/complete"
    assert client.post(url, json={"evidence_path": "x"}, headers=h).status_code == 400
    assert client.post(url, json={"reading": 200}, headers=h).status_code == 400
    bad = client.post("/api/uploads", files={"file": ("a.png", b"not an image", "image/png")}, headers=h)
    assert bad.status_code == 415
    assert client.post(url, json={"reading": 200, "evidence_path": "0" * 32 + ".png"}, headers=h).status_code == 400
    up = client.post("/api/uploads", files={"file": ("a.png", PNG, "image/png")}, headers=h)
    assert up.status_code == 201
    ok = client.post(url, json={"reading": 200, "evidence_path": up.json()["name"]}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "pending_verification"
    assert client.get(f"/api/uploads/{up.json()['name']}", headers=h).status_code == 200
    assert client.get(f"/api/uploads/{up.json()['name']}").status_code == 401


def test_waive_needs_reason_and_permission_and_is_audited(client, login, db, clock):
    generate(client, login, db)
    steward, sup = login(STEWARD), login(SUP)
    task = find(client, steward, "Clean walls")
    url = f"/api/checklists/instances/{task['id']}/waive"
    assert client.post(url, json={"reason": "Wall under repair"}, headers=steward).status_code == 403
    assert client.post(url, json={"reason": "no"}, headers=sup).status_code == 422
    ok = client.post(url, json={"reason": "Wall under repair"}, headers=sup)
    assert ok.json()["status"] == "waived"
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "checklist.waive"))


def test_only_manager_configures_checklists(client, login, db):
    body = {"name": "x1", "category": "x1", "location_id": loc_id(db, "MK"), "frequency": "daily"}
    for email in (STEWARD, SUP):
        assert client.post("/api/checklists/templates", json=body, headers=login(email)).status_code == 403
        assert client.post("/api/checklists/generate", json={"location_id": loc_id(db, "MK")},
                           headers=login(email)).status_code == 403
    assert client.post("/api/checklists/templates", json=body, headers=login(MGR)).status_code == 201


def test_task_edit_and_deactivate_are_audited_and_stop_generation(client, login, db, clock):
    m = login(MGR)
    templates = client.get("/api/checklists/templates", headers=m).json()
    mk_daily = next(t for t in templates if t["location_id"] == loc_id(db, "MK") and t["frequency"] == "daily")
    task = mk_daily["tasks"][0]
    assert client.delete(f"/api/checklists/tasks/{task['id']}", headers=m).status_code == 200
    generate(client, login, db)
    ids = {i["task_id"] for i in instances(client, m, location_id=loc_id(db, "MK"))}
    assert task["id"] not in ids
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "checklist.task_deactivate"))


def test_supervisor_cannot_touch_other_location_tasks(client, login, db, clock):
    generate(client, login, db)
    inst = find(client, login(MGR), "Clean drains")
    r = client.post(f"/api/checklists/instances/{inst['id']}/complete", json={}, headers=login("sup.rb@example.test"))
    assert r.status_code == 403
    assert client.get(f"/api/checklists/instances/{inst['id']}", headers=login("sup.rb@example.test")).status_code == 403


def test_assign_task_notifies_employee_and_checks_location(client, login, db, clock):
    generate(client, login, db)
    sup = login(SUP)
    emps = {e["employee_code"]: e["id"] for e in client.get("/api/employees?size=50", headers=login(MGR)).json()["items"]}
    task = find(client, sup, "Clean drains")
    url = f"/api/checklists/instances/{task['id']}/assign"
    assert client.post(url, json={"employee_id": emps["E006"]}, headers=sup).status_code == 400
    assert client.post(url, json={"employee_id": emps["E004"]}, headers=login(STEWARD)).status_code == 403
    ok = client.post(url, json={"employee_id": emps["E004"]}, headers=sup)
    assert ok.json()["assigned_employee_id"] == emps["E004"]
    assert db.scalar(select(Notification.id).where(Notification.kind == "task_assigned"))


def test_starter_templates_are_not_duplicated(client, login, db):
    m = login(MGR)
    r = client.post("/api/checklists/starter", json={"location_id": loc_id(db, "MK")}, headers=m)
    assert r.status_code == 201 and r.json()["tasks_added"] == 0
