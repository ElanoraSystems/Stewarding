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
