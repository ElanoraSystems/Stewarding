import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, InventoryItem

from .helpers import MGR, STEWARD, SUP, item_id


def post(client, h, path, body):
    return client.post(path, json=body, headers=h)


def refs(client, h, kind="crockery"):
    cat = client.get(f"/api/inventory/categories?kind={kind}", headers=h).json()[0]["id"]
    unit = client.get("/api/inventory/units", headers=h).json()[0]["id"]
    return cat, unit


def new_item(client, h, **over):
    cat, unit = refs(client, h, over.get("kind", "crockery"))
    body = {"kind": "crockery", "code": "SC-001", "name": "Saucer", "category_id": cat, "unit_id": unit, **over}
    return client.post("/api/inventory/items", json=body, headers=h)


def test_suppliers_are_unique_ignoring_case_and_spacing(client, login):
    m = login(MGR)
    assert post(client, m, "/api/suppliers", {"name": "Acme  Hotel Supplies", "email": "a@acme.example"}).status_code == 201
    dup = post(client, m, "/api/suppliers", {"name": "acme hotel   SUPPLIES"})
    assert dup.status_code == 409 and "Acme Hotel Supplies" in dup.json()["detail"]
    listed = [s["name"] for s in client.get("/api/suppliers", headers=m).json()]
    assert "Acme Hotel Supplies" in listed


def test_supplier_permissions_and_editing(client, login):
    assert post(client, login(SUP), "/api/suppliers", {"name": "Not Allowed Ltd"}).status_code == 403
    assert post(client, login(STEWARD), "/api/suppliers", {"name": "Not Allowed Ltd"}).status_code == 403
    assert client.get("/api/suppliers", headers=login(STEWARD)).status_code == 403
    assert client.get("/api/suppliers", headers=login(SUP)).status_code == 200
    m = login(MGR)
    a = post(client, m, "/api/suppliers", {"name": "Alpha Ware"}).json()
    b = post(client, m, "/api/suppliers", {"name": "Beta Ware"}).json()
    assert client.put(f"/api/suppliers/{b['id']}", json={"name": "ALPHA ware"}, headers=m).status_code == 409
    assert client.put(f"/api/suppliers/{a['id']}", json={"name": "ALPHA WARE", "phone": "555"}, headers=m).json()["name"] == "ALPHA WARE"
    assert client.put("/api/suppliers/9999", json={"phone": "1"}, headers=m).status_code == 404


def test_inactive_supplier_is_hidden_and_cannot_be_linked(client, login, db):
    m = login(MGR)
    s = post(client, m, "/api/suppliers", {"name": "Closing Down Ltd"}).json()
    assert new_item(client, m, supplier_id=s["id"]).status_code == 201
    client.put(f"/api/suppliers/{s['id']}", json={"active": False}, headers=m)
    assert s["id"] not in [x["id"] for x in client.get("/api/suppliers", headers=m).json()]
    assert s["id"] in [x["id"] for x in client.get("/api/suppliers?include_inactive=true", headers=m).json()]
    assert new_item(client, m, code="SC-002", name="Another Saucer", supplier_id=s["id"]).status_code == 400


def test_item_names_are_unique_per_type_ignoring_case_and_spacing(client, login, db):
    m = login(MGR)
    dup = new_item(client, m, code="DP-009", name="  dinner   PLATE 27cm ")
    assert dup.status_code == 409 and "Dinner Plate 27cm (PL-001)" in dup.json()["detail"]
    other_kind = new_item(client, m, kind="smallware", code="TY-001", name="Soup Bowl")
    assert other_kind.status_code == 201  # the same name is fine under a different inventory type


def test_item_codes_are_unique_and_normalised(client, login):
    m = login(MGR)
    dup = new_item(client, m, code=" pl-001 ", name="Brand New Plate")
    assert dup.status_code == 409 and "PL-001" in dup.json()["detail"]
    ok = new_item(client, m, code=" nw-001 ", name="Brand New Plate")
    assert ok.status_code == 201 and ok.json()["code"] == "NW-001"


def test_renaming_checks_duplicates_but_allows_recasing_itself(client, login, db):
    m = login(MGR)
    plate = item_id(db, "PL-001")
    assert client.put(f"/api/inventory/items/{plate}", json={"name": "side plate 18cm"}, headers=m).status_code == 409
    assert client.put(f"/api/inventory/items/{plate}", json={"name": "DINNER PLATE 27CM"}, headers=m).status_code == 200
    again = new_item(client, m, code="DP-010", name="dinner plate 27cm")
    assert again.status_code == 409


def test_inactive_duplicate_points_to_reactivation(client, login, db):
    m = login(MGR)
    client.put(f"/api/inventory/items/{item_id(db, 'PL-002')}", json={"active": False}, headers=m)
    dup = new_item(client, m, code="SP-009", name="Side Plate 18cm")
    assert dup.status_code == 409 and "reactivate" in dup.json()["detail"]


def test_similar_name_lookup_warns_before_a_duplicate_is_created(client, login):
    m = login(MGR)
    found = client.get("/api/inventory/items/lookup?q=dinner pl", headers=m).json()
    assert [i["code"] for i in found] == ["PL-001"]
    assert client.get("/api/inventory/items/lookup?q=di", headers=m).json() == []
    assert client.get("/api/inventory/items/lookup?q=bowl&kind=smallware", headers=m).json() == []
    assert client.get("/api/inventory/items/lookup?q=dinner", headers=login(STEWARD)).status_code == 200


def test_database_itself_refuses_duplicate_item_names(db):
    first = db.scalar(select(InventoryItem))
    db.add(InventoryItem(kind=first.kind, code="ZZ-1", name="Whatever", name_key=first.name_key, category_id=first.category_id,
                         unit_id=first.unit_id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_item_is_linked_to_its_supplier_and_costs_stay_hidden_from_stewards(client, login):
    m = login(MGR)
    supplier = client.get("/api/suppliers", headers=m).json()[0]
    item = client.get("/api/inventory/items?kind=crockery", headers=m).json()["items"][0]
    assert item["supplier"] == "Gulf Catering Supplies" and item["supplier_id"] == supplier["id"]
    steward_view = client.get("/api/inventory/items?kind=crockery", headers=login(STEWARD)).json()["items"][0]
    assert steward_view["supplier"] is None and "unit_cost" not in steward_view


def test_categories_and_units_are_unique_renameable_and_can_be_retired(client, login, db):
    m = login(MGR)
    assert post(client, m, "/api/inventory/categories", {"kind": "crockery", "name": " plates "}).status_code == 409
    created = post(client, m, "/api/inventory/categories", {"kind": "crockery", "name": "Glass Jugs"}).json()
    assert post(client, m, "/api/inventory/categories", {"kind": "smallware", "name": "glass jugs"}).status_code == 201
    assert client.put(f"/api/inventory/categories/{created['id']}", json={"name": "BOWLS"}, headers=m).status_code == 409
    assert client.put(f"/api/inventory/categories/{created['id']}", json={"name": "Glass Carafes"}, headers=m).json()["name"] == "Glass Carafes"
    client.put(f"/api/inventory/categories/{created['id']}", json={"active": False}, headers=m)
    assert created["id"] not in [c["id"] for c in client.get("/api/inventory/categories?kind=crockery", headers=m).json()]
    assert created["id"] in [c["id"] for c in client.get("/api/inventory/categories?kind=crockery&include_inactive=true", headers=m).json()]
    unit = client.get("/api/inventory/units", headers=m).json()[0]["id"]
    assert new_item(client, m, category_id=created["id"], unit_id=unit).status_code == 400

    assert post(client, m, "/api/inventory/units", {"name": " EACH"}).status_code == 409
    box = post(client, m, "/api/inventory/units", {"name": "Box"}).json()
    client.put(f"/api/inventory/units/{box['id']}", json={"active": False}, headers=m)
    cat = client.get("/api/inventory/categories?kind=crockery", headers=m).json()[0]["id"]
    assert new_item(client, m, category_id=cat, unit_id=box["id"]).status_code == 400
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "inventory.category_update"))


@pytest.mark.parametrize("who", [SUP, STEWARD])
def test_only_managers_change_inventory_lists(client, login, who):
    h = login(who)
    assert client.put("/api/inventory/categories/1", json={"name": "X1"}, headers=h).status_code == 403
    assert client.put("/api/inventory/units/1", json={"name": "X1"}, headers=h).status_code == 403
    assert client.put("/api/suppliers/1", json={"name": "X1"}, headers=h).status_code == 403


def test_every_role_can_read_the_managed_lists_but_only_managers_edit_them(client, login):
    for who in (MGR, SUP, STEWARD):
        lists = client.get("/api/lookups", headers=login(who)).json()
        assert set(lists) == {"job_title", "checklist_category", "breakage_reason", "corrective_action"}
        assert "Cleaning" in [v["value"] for v in lists["checklist_category"]]
    assert client.get("/api/lookups").status_code == 401
    assert post(client, login(SUP), "/api/lookups", {"kind": "job_title", "value": "Head Steward"}).status_code == 403
    assert post(client, login(STEWARD), "/api/lookups", {"kind": "job_title", "value": "Head Steward"}).status_code == 403


def test_lookup_values_are_unique_editable_and_retire_instead_of_delete(client, login, db):
    m = login(MGR)
    dup = post(client, m, "/api/lookups", {"kind": "breakage_reason", "value": "  dropped WHILE carrying"})
    assert dup.status_code == 409
    new = post(client, m, "/api/lookups", {"kind": "breakage_reason", "value": "Tray overloaded"})
    assert new.status_code == 201
    assert post(client, m, "/api/lookups", {"kind": "job_title", "value": "Tray overloaded"}).status_code == 201
    assert client.put(f"/api/lookups/{new.json()['id']}", json={"value": "cause unknown"}, headers=m).status_code == 409
    client.put(f"/api/lookups/{new.json()['id']}", json={"active": False}, headers=m)
    reasons = client.get("/api/lookups?kind=breakage_reason", headers=m).json()
    assert "Tray overloaded" not in [v["value"] for v in reasons]
    assert "Tray overloaded" in [v["value"] for v in client.get("/api/lookups?kind=breakage_reason&include_inactive=true", headers=m).json()]
    assert post(client, m, "/api/lookups", {"kind": "colour", "value": "Blue"}).status_code == 422
    assert client.delete(f"/api/lookups/{new.json()['id']}", headers=m).status_code in (404, 405)
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "lookup.create"))
