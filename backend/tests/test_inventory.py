import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, StockTransaction

from .helpers import MGR, STEWARD, SUP, SUP_RB, balance, item_id, ledger_sum, loc_id


def txn(client, h, db, code, loc, kind, qty, reason=None):
    body = {"item_id": item_id(db, code), "location_id": loc_id(db, loc), "txn_type": kind, "qty": qty, "reason": reason}
    return client.post("/api/inventory/transactions", json=body, headers=h)


def test_seed_balances_match_the_ledger(db):
    for code, loc in (("PL-001", "MK"), ("PL-001", "RB"), ("UT-001", "BQ"), ("KN-001", "MK")):
        assert balance(db, code, loc) == ledger_sum(db, code, loc) > 0


def test_manager_creates_item_with_opening_stock_posted_to_the_ledger(client, login, db):
    m = login(MGR)
    cats = client.get("/api/inventory/categories?kind=crockery", headers=m).json()
    units = client.get("/api/inventory/units", headers=m).json()
    body = {"kind": "crockery", "code": "SC-001", "name": "Saucer", "category_id": cats[0]["id"], "unit_id": units[0]["id"],
            "min_level": 10, "unit_cost": 1.2, "opening_qty": 80, "opening_location_id": loc_id(db, "MK")}
    r = client.post("/api/inventory/items", json=body, headers=m)
    assert r.status_code == 201 and r.json()["qty"] == 80
    assert balance(db, "SC-001", "MK") == ledger_sum(db, "SC-001", "MK") == 80
    assert client.post("/api/inventory/items", json=body, headers=m).status_code == 409
    wrong_kind = {**body, "code": "SC-002", "kind": "smallware"}
    assert client.post("/api/inventory/items", json=wrong_kind, headers=m).status_code == 400
    no_location = {**body, "code": "SC-003", "opening_location_id": None}
    assert client.post("/api/inventory/items", json=no_location, headers=m).status_code == 400


@pytest.mark.parametrize("email", [SUP, STEWARD])
def test_only_manager_edits_master_data(client, login, db, email):
    h = login(email)
    assert client.post("/api/inventory/items", json={}, headers=h).status_code in (403, 422)
    assert client.put(f"/api/inventory/items/{item_id(db, 'PL-001')}", json={"min_level": 1}, headers=h).status_code == 403
    assert client.post("/api/inventory/categories", json={"kind": "crockery", "name": "Jugs"}, headers=h).status_code == 403
    assert client.post("/api/inventory/units", json={"name": "Box"}, headers=h).status_code == 403


def test_manager_can_configure_categories_units_and_items(client, login, db):
    m = login(MGR)
    assert client.post("/api/inventory/categories", json={"kind": "crockery", "name": "Jugs"}, headers=m).status_code == 201
    assert client.post("/api/inventory/categories", json={"kind": "crockery", "name": "Jugs"}, headers=m).status_code == 409
    assert client.post("/api/inventory/units", json={"name": "Box"}, headers=m).status_code == 201
    r = client.put(f"/api/inventory/items/{item_id(db, 'PL-001')}", json={"min_level": 99}, headers=m)
    assert r.json()["min_level"] == 99
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "inventory.item_update"))


def test_steward_can_view_items_but_not_costs(client, login):
    steward = client.get("/api/inventory/items?kind=crockery", headers=login(STEWARD)).json()
    assert steward["items"] and all("unit_cost" not in i and "value" not in i for i in steward["items"])
    assert "total_value" not in steward
    manager = client.get("/api/inventory/items?kind=crockery", headers=login(MGR)).json()
    assert manager["items"][0]["unit_cost"] and manager["total_value"] > 0


def test_receipt_issue_return_move_stock_and_stay_in_step_with_the_ledger(client, login, db):
    h = login(SUP)
    assert txn(client, h, db, "PL-001", "MK", "receipt", 50).status_code == 201
    assert txn(client, h, db, "PL-001", "MK", "issue", 30).status_code == 201
    assert txn(client, h, db, "PL-001", "MK", "return", 5).status_code == 201
    assert balance(db, "PL-001", "MK") == 225 == ledger_sum(db, "PL-001", "MK")


def test_issue_beyond_stock_is_refused_and_changes_nothing(client, login, db):
    h = login(SUP)
    before = db.scalar(select(StockTransaction.id).order_by(StockTransaction.id.desc()))
    assert txn(client, h, db, "PL-001", "MK", "issue", 500).status_code == 409
    assert balance(db, "PL-001", "MK") == 200
    assert db.scalar(select(StockTransaction.id).order_by(StockTransaction.id.desc())) == before


def test_posting_rules_and_permissions(client, login, db):
    assert txn(client, login(STEWARD), db, "PL-001", "MK", "receipt", 5).status_code == 403
    assert txn(client, login(SUP), db, "PL-001", "RB", "receipt", 5).status_code == 403
    assert txn(client, login(SUP), db, "PL-001", "MK", "receipt", 0).status_code == 400
    assert txn(client, login(SUP), db, "PL-001", "MK", "receipt", -3).status_code == 400
    assert txn(client, login(SUP), db, "PL-001", "MK", "damage", 2).status_code == 400  # reason required
    assert txn(client, login(SUP), db, "PL-001", "MK", "damage", 2, "Dropped in sink").status_code == 201


def test_adjustment_needs_manager_reason_and_is_audited(client, login, db):
    assert txn(client, login(SUP), db, "PL-001", "MK", "adjustment", -3, "Count correction").status_code == 403
    m = login(MGR)
    assert txn(client, m, db, "PL-001", "MK", "adjustment", -3).status_code == 400
    assert txn(client, m, db, "PL-001", "MK", "adjustment", 0, "No change here").status_code == 400
    assert txn(client, m, db, "PL-001", "MK", "adjustment", -3, "Count correction").status_code == 201
    assert txn(client, m, db, "PL-001", "MK", "adjustment", 4, "Found in other store").status_code == 201
    assert balance(db, "PL-001", "MK") == 201 == ledger_sum(db, "PL-001", "MK")
    assert len(db.scalars(select(AuditLog).where(AuditLog.action == "inventory.adjustment")).all()) == 2


def test_stock_transactions_are_immutable(client, login, db):
    txn(client, login(SUP), db, "PL-001", "MK", "receipt", 5)
    row_ = db.scalar(select(StockTransaction).order_by(StockTransaction.id.desc()))
    row_.qty_delta = 999
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()
    db.delete(db.scalar(select(StockTransaction).order_by(StockTransaction.id.desc())))
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()
    last = db.scalar(select(StockTransaction.id).order_by(StockTransaction.id.desc()))
    assert client.put(f"/api/inventory/transactions/{last}", json={}, headers=login(MGR)).status_code in (404, 405)
    assert client.delete(f"/api/inventory/transactions/{last}", headers=login(MGR)).status_code in (404, 405)


def test_low_stock_alert_fires_once_per_day(client, login, db):
    h = login(SUP)
    txn(client, h, db, "UT-001", "MK", "issue", 8)  # 12 -> 4, minimum is 5
    txn(client, h, db, "UT-001", "MK", "issue", 1)
    alerts = db.scalars(select(Notification).where(Notification.kind == "low_stock")).all()
    assert alerts and len({(a.user_id, a.dedupe_key) for a in alerts}) == len(alerts)
    assert {a.title.split(":")[1].split("(")[0].strip() for a in alerts} == {"Ladle"}


def test_balances_are_scoped_to_the_callers_locations(client, login, db):
    sup_rb = client.get("/api/inventory/items?kind=crockery", headers=login(SUP_RB)).json()["items"]
    plate = next(i for i in sup_rb if i["code"] == "PL-001")
    assert plate["qty"] == 40 and set(plate["by_location"]) == {str(loc_id(db, "RB"))}
    manager = next(i for i in client.get("/api/inventory/items?kind=crockery", headers=login(MGR)).json()["items"]
                   if i["code"] == "PL-001")
    assert manager["qty"] == 390
    assert client.get(f"/api/inventory/items?kind=crockery&location_id={loc_id(db, 'MK')}", headers=login(SUP_RB)).status_code == 403


def test_search_low_only_and_pagination(client, login, db):
    m = login(MGR)
    assert [i["code"] for i in client.get("/api/inventory/items?kind=smallware&search=knife", headers=m).json()["items"]] == ["KN-001"]
    rb_low = client.get(f"/api/inventory/items?kind=crockery&low_only=true&location_id={loc_id(db, 'RB')}", headers=m).json()
    assert "PL-001" in {i["code"] for i in rb_low["items"]}
    page = client.get("/api/inventory/items?kind=crockery&size=2&page=2", headers=m).json()
    assert page["total"] == 5 and len(page["items"]) == 2


def test_transaction_history_is_scoped_and_filterable(client, login, db):
    txn(client, login(SUP), db, "PL-001", "MK", "receipt", 5)
    mine = client.get(f"/api/inventory/transactions?txn_type=receipt", headers=login(SUP)).json()
    assert mine["total"] == 1 and mine["items"][0]["user"] == "Sam Supervisor"
    assert client.get("/api/inventory/transactions?txn_type=receipt", headers=login(SUP_RB)).json()["total"] == 0


def test_tracked_assets(client, login, db):
    m = login(MGR)
    knife = item_id(db, "KN-001")
    plate = item_id(db, "PL-001")
    body = {"item_id": knife, "asset_tag": "KN-MK-99", "location_id": loc_id(db, "MK")}
    assert client.post("/api/inventory/assets", json={**body, "item_id": plate}, headers=m).status_code == 400
    created = client.post("/api/inventory/assets", json=body, headers=m)
    assert created.status_code == 201
    assert client.post("/api/inventory/assets", json=body, headers=m).status_code == 409
    url = f"/api/inventory/assets/{created.json()['id']}"
    assert client.put(url, json={"condition": "damaged"}, headers=login(STEWARD)).status_code == 403
    assert client.put(url, json={"condition": "damaged"}, headers=login(SUP_RB)).status_code == 403
    assert client.put(url, json={"condition": "damaged"}, headers=login(SUP)).json()["condition"] == "damaged"
