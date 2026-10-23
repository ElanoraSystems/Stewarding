from sqlalchemy import select

from app.models import AuditLog, InventoryItem, Supplier

from .helpers import MGR, STEWARD, SUP, loc_id


def test_an_unused_location_is_deleted_and_audited(client, login, db):
    m = login(MGR)
    made = client.post("/api/settings/locations", json={"code": "TMP", "name": "Temporary Site", "kind": "other", "timezone": "Asia/Kuwait"}, headers=m)
    assert made.status_code == 201
    gone = client.delete(f"/api/settings/locations/{made.json()['id']}", headers=m)
    assert gone.status_code == 200 and gone.json() == {"deleted": made.json()["id"]}
    assert all(loc["code"] != "TMP" for loc in client.get("/api/settings", headers=m).json()["locations"])
    entry = db.scalars(select(AuditLog).where(AuditLog.action == "location.delete")).one()
    assert entry.before == {"code": "TMP", "name": "Temporary Site"}


def test_a_location_in_use_is_refused_with_what_uses_it(client, login, db):
    m = login(MGR)
    r = client.delete(f"/api/settings/locations/{loc_id(db, 'MK')}", headers=m)
    assert r.status_code == 409 and "used by" in r.json()["detail"] and "make it inactive instead" in r.json()["detail"]
    assert client.delete("/api/settings/locations/99999", headers=m).status_code == 404


def test_only_managers_delete_settings_records(client, login, db):
    for email in (SUP, STEWARD):
        h = login(email)
        assert client.delete(f"/api/settings/locations/{loc_id(db, 'MK')}", headers=h).status_code == 403
        assert client.delete("/api/roster/shifts/1", headers=h).status_code == 403
        assert client.delete("/api/lookups/1", headers=h).status_code == 403


def test_an_unused_shift_is_deleted_but_one_with_assignments_is_not(client, login, db):
    m = login(MGR)
    body = {"name": "Split", "start_time": "09:00", "end_time": "17:00"}
    free = client.post("/api/roster/shifts", json=body, headers=m).json()
    assert client.delete(f"/api/roster/shifts/{free['id']}", headers=m).status_code == 200
    used = client.post("/api/roster/shifts", json={**body, "name": "Split two"}, headers=m).json()
    employee = client.get("/api/employees?size=1", headers=m).json()["items"][0]
    assigned = client.post("/api/roster/assignments", headers=m, json={
        "employee_id": employee["id"], "shift_id": used["id"], "location_id": employee["location_ids"][0], "weekdays": [2], "valid_from": "2030-01-01"})
    assert assigned.status_code == 201, assigned.text
    r = client.delete(f"/api/roster/shifts/{used['id']}", headers=m)
    assert r.status_code == 409 and "roster assignments" in r.json()["detail"]


def test_lists_categories_and_units_delete_when_unused(client, login):
    m = login(MGR)
    value = client.post("/api/lookups", json={"kind": "corrective_action", "value": "Move to the cold room"}, headers=m).json()
    assert client.delete(f"/api/lookups/{value['id']}", headers=m).status_code == 200
    category = client.post("/api/inventory/categories", json={"name": "Spare category"}, headers=m).json()
    assert client.delete(f"/api/inventory/categories/{category['id']}", headers=m).status_code == 200
    unit = client.post("/api/inventory/units", json={"name": "Spare unit"}, headers=m).json()
    assert client.delete(f"/api/inventory/units/{unit['id']}", headers=m).status_code == 200


def test_a_category_or_unit_that_items_use_is_refused(client, login, db):
    m = login(MGR)
    item = db.scalars(select(InventoryItem)).first()
    cat = client.delete(f"/api/inventory/categories/{item.category_id}", headers=m)
    unit = client.delete(f"/api/inventory/units/{item.unit_id}", headers=m)
    assert cat.status_code == 409 and "items" in cat.json()["detail"]
    assert unit.status_code == 409 and "items" in unit.json()["detail"]


def test_a_supplier_is_deleted_unless_items_use_it(client, login, db):
    m = login(MGR)
    free = client.post("/api/suppliers", json={"name": "Spare Supplier"}, headers=m).json()
    assert client.delete(f"/api/suppliers/{free['id']}", headers=m).status_code == 200
    used = client.post("/api/suppliers", json={"name": "Busy Supplier"}, headers=m).json()
    item = db.scalars(select(InventoryItem)).first()
    assert client.put(f"/api/inventory/items/{item.id}", json={"supplier_id": used["id"]}, headers=m).status_code == 200
    r = client.delete(f"/api/suppliers/{used['id']}", headers=m)
    assert r.status_code == 409 and "items" in r.json()["detail"]
    assert db.scalar(select(Supplier.id).where(Supplier.id == used["id"])) == used["id"]


def test_an_item_with_no_history_is_deleted_but_one_with_stock_is_not(client, login, db):
    m = login(MGR)
    item = db.scalars(select(InventoryItem)).first()
    fresh = client.post("/api/inventory/items", json={"name": "Spare Tray", "category_id": item.category_id, "unit_id": item.unit_id}, headers=m).json()
    assert client.delete(f"/api/inventory/items/{fresh['id']}", headers=m).status_code == 200
    r = client.delete(f"/api/inventory/items/{item.id}", headers=m)
    assert r.status_code == 409 and "make it inactive instead" in r.json()["detail"]
