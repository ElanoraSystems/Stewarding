from .helpers import MGR, STEWARD, SUP, loc_id


def test_blank_lookup_supplier_email_and_duplicate_names_are_refused(client, login, db, clock):
    m = login(MGR)
    assert client.post("/api/lookups", json={"kind": "monitoring_type", "value": "   "}, headers=m).status_code == 422
    assert client.post("/api/suppliers", json={"name": "Mail Co", "email": "not-an-email"}, headers=m).status_code == 422
    assert client.post("/api/suppliers", json={"name": "Mail Co", "email": "ok@mail.co"}, headers=m).status_code == 201
    shift = {"name": "QA Split", "start_time": "10:00:00", "end_time": "18:00:00"}
    assert client.post("/api/roster/shifts", json=shift, headers=m).status_code == 201
    assert client.post("/api/roster/shifts", json={**shift, "name": "qa split"}, headers=m).status_code == 409
    template = {"name": "QA Opening", "category": "Opening", "location_id": loc_id(db, "MK"), "frequency": "daily"}
    made = client.post("/api/checklists/templates", json=template, headers=m)
    assert made.status_code == 201 and client.post("/api/checklists/templates", json={**template, "name": "qa opening"}, headers=m).status_code == 409


def test_checklist_task_rules_and_unknown_references(client, login, db, clock):
    m = login(MGR)
    template = client.post("/api/checklists/templates", headers=m, json={"name": "QA Tasks", "category": "Opening", "location_id": loc_id(db, "MK"), "frequency": "daily"}).json()
    url = f"/api/checklists/templates/{template['id']}/tasks"
    assert client.post(url, json={"description": "Wipe benches", "scheduled_time": "09:00:00", "deadline_time": "06:00:00"}, headers=m).status_code == 422
    assert client.post(url, json={"description": "Wipe benches", "active_from": "2026-10-10", "active_to": "2026-10-01"}, headers=m).status_code == 422
    assert client.post(url, json={"description": "Wipe benches", "assigned_employee_id": 99999}, headers=m).status_code == 400
    assert client.post(url, json={"description": "Wipe benches", "shift_id": 99999}, headers=m).status_code == 400
    assert client.post(url, json={"description": "Wipe benches", "scheduled_time": "06:00:00", "deadline_time": "09:00:00"}, headers=m).status_code == 201


def test_stock_reports_are_for_the_inventory_module_only(client, login, db, clock):
    mk = loc_id(db, "MK")
    for url in ("/api/stock/insights", f"/api/stock/reconciliation?location_id={mk}&month=2026-03", "/api/stock/transfers", "/api/inventory/transactions"):
        assert client.get(url, headers=login(STEWARD)).status_code == 403, url
        assert client.get(url, headers=login(SUP)).status_code == 200, url


def test_an_employee_has_an_optional_company_that_can_be_searched_and_changed(client, login, db, clock):
    m = login(MGR)
    body = {"employee_code": "E500", "full_name": "Contract Cook", "job_title": "Cook", "company": "  Gulf Catering Co  ", "email": "cook@example.com",
            "password": "qa-pass-12345", "role": "steward", "location_ids": [loc_id(db, "MK")]}
    made = client.post("/api/employees", json=body, headers=m)
    assert made.status_code == 201 and made.json()["company"] == "Gulf Catering Co"
    assert [e["employee_code"] for e in client.get("/api/employees?search=catering", headers=m).json()["items"]] == ["E500"]
    changed = client.put(f"/api/employees/{made.json()['id']}", json={"company": "Sea Staffing"}, headers=m)
    assert changed.json()["company"] == "Sea Staffing"
    assert client.post("/api/employees", json={**body, "employee_code": "E501", "email": "own@example.com", "company": None}, headers=m).json()["company"] is None
    assert client.post("/api/employees", json={**body, "employee_code": "E502", "email": "long@example.com", "company": "x" * 121}, headers=m).status_code == 422


def test_alerts_are_acknowledged_in_bulk_and_only_your_own(client, login, db, clock):
    from app.models import Notification, User
    from sqlalchemy import select
    sup, mgr = login(SUP), login(MGR)
    me = db.scalar(select(User).where(User.email == SUP))
    other = db.scalar(select(User).where(User.email == MGR))
    made = [Notification(user_id=u.id, kind="monitoring_failed", title=f"Failed {n}", requires_ack=True, priority="critical", dedupe_key=f"qa:{u.id}:{n}")
            for u in (me, other) for n in range(3)]
    db.add_all(made)
    db.commit()
    mine = [n.id for n in made if n.user_id == me.id]
    theirs = [n.id for n in made if n.user_id == other.id]
    assert client.post("/api/notifications/acknowledge-many", json={"ids": mine[:2] + theirs}, headers=sup).json() == {"acknowledged": 2}
    assert client.post("/api/notifications/acknowledge-many", json={}, headers=sup).json() == {"acknowledged": 1}
    assert client.post("/api/notifications/acknowledge-many", json={}, headers=sup).json() == {"acknowledged": 0}
    assert client.post("/api/notifications/acknowledge-many", json={}, headers=mgr).json() == {"acknowledged": 3}


def test_checklist_tasks_are_approved_in_bulk(client, login, db, clock):
    mk = loc_id(db, "MK")
    m, steward, sup = login(MGR), login(STEWARD), login(SUP)
    template = client.post("/api/checklists/templates", headers=m, json={"name": "QA Bulk", "category": "Opening", "location_id": mk, "frequency": "daily"}).json()
    for n in range(2):
        client.post(f"/api/checklists/templates/{template['id']}/tasks", headers=m, json={"description": f"Bulk task {n}", "requires_verification": True})
    client.post("/api/checklists/generate", json={"location_id": mk}, headers=m)
    items = [i for i in client.get(f"/api/checklists/instances?location_id={mk}&size=200", headers=m).json()["items"] if i["description"].startswith("Bulk task")]
    for i in items:
        assert client.post(f"/api/checklists/instances/{i['id']}/complete", json={}, headers=steward).status_code == 200
    ids = [i["id"] for i in items]
    assert client.post("/api/checklists/instances/verify-many", json={"instance_ids": ids}, headers=steward).status_code == 403
    assert client.post("/api/checklists/instances/verify-many", json={"instance_ids": ids}, headers=sup).json() == {"approved": 2, "skipped": 0}
    assert client.post("/api/checklists/instances/verify-many", json={"instance_ids": ids}, headers=sup).json() == {"approved": 0, "skipped": 2}
    assert {client.get(f"/api/checklists/instances/{i}", headers=m).json()["status"] for i in ids} == {"verified"}


def test_the_employee_id_is_generated_when_left_blank_and_never_repeats(client, login, db, clock):
    m = login(MGR)
    body = {"full_name": "Auto Id", "job_title": "Cook", "email": "auto1@example.com", "password": "qa-pass-12345", "role": "steward", "location_ids": [loc_id(db, "MK")]}
    first = client.post("/api/employees", json=body, headers=m)
    second = client.post("/api/employees", json={**body, "email": "auto2@example.com"}, headers=m)
    assert (first.status_code, second.status_code) == (201, 201)
    assert (first.json()["employee_code"], second.json()["employee_code"]) == ("E007", "E008")
    typed = client.post("/api/employees", json={**body, "email": "auto3@example.com", "employee_code": "X-900"}, headers=m)
    assert typed.json()["employee_code"] == "X-900"
    assert client.post("/api/employees", json={**body, "email": "auto4@example.com"}, headers=m).json()["employee_code"] == "E009"


def test_checklist_tasks_are_assigned_and_waived_in_bulk(client, login, db, clock):
    mk = loc_id(db, "MK")
    m, sup, steward = login(MGR), login(SUP), login(STEWARD)
    template = client.post("/api/checklists/templates", headers=m, json={"name": "QA Many", "category": "Opening", "location_id": mk, "frequency": "daily"}).json()
    for n in range(3):
        client.post(f"/api/checklists/templates/{template['id']}/tasks", headers=m, json={"description": f"Many task {n}"})
    client.post("/api/checklists/generate", json={"location_id": mk}, headers=m)
    items = [i for i in client.get(f"/api/checklists/instances?location_id={mk}&size=200", headers=m).json()["items"] if i["description"].startswith("Many task")]
    ids = [i["id"] for i in items]
    sid = next(e["id"] for e in client.get("/api/employees?size=50", headers=m).json()["items"] if e["employee_code"] == "E004")
    rita = next(e["id"] for e in client.get("/api/employees?size=50", headers=m).json()["items"] if e["employee_code"] == "E003")
    assert client.post("/api/checklists/instances/assign-many", json={"instance_ids": ids, "employee_id": sid}, headers=steward).status_code == 403
    assert client.post("/api/checklists/instances/assign-many", json={"instance_ids": ids, "employee_id": 9999}, headers=sup).status_code == 400
    assert client.post("/api/checklists/instances/assign-many", json={"instance_ids": ids, "employee_id": rita}, headers=sup).json() == {"assigned": 0, "skipped": 3}
    assert client.post("/api/checklists/instances/assign-many", json={"instance_ids": ids, "employee_id": sid}, headers=sup).json() == {"assigned": 3, "skipped": 0}
    assert {client.get(f"/api/checklists/instances/{i}", headers=m).json()["assigned_employee_id"] for i in ids} == {sid}
    assert client.post("/api/checklists/instances/waive-many", json={"instance_ids": ids, "reason": "x"}, headers=sup).status_code == 422
    assert client.post("/api/checklists/instances/waive-many", json={"instance_ids": ids, "reason": "Closed for deep clean"}, headers=sup).json() == {"waived": 3, "skipped": 0}
    assert client.post("/api/checklists/instances/waive-many", json={"instance_ids": ids, "reason": "Closed for deep clean"}, headers=sup).json() == {"waived": 0, "skipped": 3}
    assert client.post("/api/checklists/instances/assign-many", json={"instance_ids": ids, "employee_id": sid}, headers=sup).json() == {"assigned": 0, "skipped": 3}
