from decimal import Decimal

from sqlalchemy import select

from app.models import InventoryBalance, StockTransaction

from .helpers import MGR, SUP, loc_id

TODAY = "2026-03-02"
URL = "/api/stock/cost-report"


def item_and_supplier(client, login, db, cost=None):
    m = login(MGR)
    cat = client.get("/api/inventory/categories", headers=m).json()[0]["id"]
    unit = client.get("/api/inventory/units", headers=m).json()[0]["id"]
    item = client.post("/api/inventory/items", headers=m, json={"name": "Costing Plate", "category_id": cat, "unit_id": unit, "min_level": 1, **({"unit_cost": cost} if cost else {})}).json()
    sup = client.post("/api/suppliers", headers=m, json={"name": "Costing Supplier"}).json()
    return item, sup


def receive(client, login, db, item, sup, qty, cost, invoice, **extra):
    return client.post("/api/receipts", headers=login(SUP), json={"supplier_id": sup["id"], "location_id": loc_id(db, "MK"), "invoice_number": invoice,
                       "lines": [{"item_id": item["id"], "qty": qty, "unit_cost": cost}], **extra})


def average(db, item):
    db.expire_all()
    return db.get(InventoryBalance, (item["id"], loc_id(db, "MK"))).avg_cost


def test_receipts_blend_into_the_average_and_issues_leave_it_alone(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    assert receive(client, login, db, item, sup, 10, 2.00, "W-1").status_code == 201
    assert average(db, item) == Decimal("2.0000")
    assert receive(client, login, db, item, sup, 20, 2.60, "W-2").status_code == 201
    assert average(db, item) == Decimal("2.4000")                      # (10 x 2.00 + 20 x 2.60) / 30
    client.post("/api/inventory/transactions", headers=login(SUP), json={"item_id": item["id"], "location_id": loc_id(db, "MK"), "txn_type": "issue", "qty": 6})
    assert average(db, item) == Decimal("2.4000")
    issue = db.scalars(select(StockTransaction).where(StockTransaction.item_id == item["id"], StockTransaction.txn_type == "issue")).one()
    assert issue.unit_cost == Decimal("2.4000")
    assert receive(client, login, db, item, sup, 6, 3.00, "W-3").status_code == 201
    assert average(db, item) == Decimal("2.5200")                      # (24 x 2.40 + 6 x 3.00) / 30


def test_a_discount_is_part_of_the_cost(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    receive(client, login, db, item, sup, 10, 5.00, "W-D", discount_type="percent", discount=10)
    assert average(db, item) == Decimal("4.5000")                      # an invoice discount lowers the cost of every unit
    line = client.post("/api/receipts", headers=login(SUP), json={"supplier_id": sup["id"], "location_id": loc_id(db, "MK"), "invoice_number": "W-D2",
                       "lines": [{"item_id": item["id"], "qty": 10, "unit_cost": 5.00, "discount_type": "amount", "discount": 10}]})
    assert line.status_code == 201 and average(db, item) == Decimal("4.2500")   # (10 x 4.50 + 10 x 4.00) / 20


def test_voiding_a_receipt_takes_its_price_back_out_of_the_average(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    receive(client, login, db, item, sup, 10, 2.00, "W-V1")
    second = receive(client, login, db, item, sup, 10, 4.00, "W-V2").json()
    assert average(db, item) == Decimal("3.0000")
    assert client.post(f"/api/receipts/{second['id']}/void", headers=login(MGR), json={"reason": "Entered by mistake"}).status_code == 200
    assert average(db, item) == Decimal("2.0000")


def test_a_transfer_carries_the_sending_average_into_the_receiving_location(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    receive(client, login, db, item, sup, 10, 2.00, "W-T1")
    receive(client, login, db, item, sup, 10, 3.00, "W-T2")                  # average 2.50 at Main Kitchen
    made = client.post("/api/stock/transfers", headers=login(SUP), json={"from_location_id": loc_id(db, "MK"), "to_location_id": loc_id(db, "BQ"), "lines": [{"item_id": item["id"], "qty": 4}]}).json()
    client.post(f"/api/stock/transfers/{made['id']}/decision", headers=login(MGR), json={"approve": True})
    db.expire_all()
    there = db.get(InventoryBalance, (item["id"], loc_id(db, "BQ")))
    assert there.qty == 4 and there.avg_cost == Decimal("2.5000")


def test_the_cost_report_adds_up_to_the_cost_consumed(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    m = login(MGR)
    receive(client, login, db, item, sup, 10, 2.00, "W-R1")
    receive(client, login, db, item, sup, 20, 2.60, "W-R2")                  # average 2.40, 30 in stock
    client.post("/api/inventory/transactions", headers=login(SUP), json={"item_id": item["id"], "location_id": loc_id(db, "MK"), "txn_type": "issue", "qty": 5})
    incident = client.post("/api/breakage", headers=login("steward.mk@example.test"), json={"location_id": loc_id(db, "MK"), "item_id": item["id"], "qty": 2, "incident_type": "breakage", "reason": "dropped"}).json()
    client.post(f"/api/breakage/{incident['id']}/review", headers=login(SUP), json={"qty": 2, "reason": "confirmed"})
    report = client.get(f"{URL}?location_id={loc_id(db, 'MK')}&date_from=2026-03-01&date_to=2026-03-31", headers=m).json()
    row = next(r for r in report["rows"] if r["item_id"] == item["id"])
    assert row["purchases"] == 10 * 2.00 + 20 * 2.60 == 72.0
    assert row["issued"] == 12.0 and row["breakage_damage"] == 4.8        # 5 and 2 units at 2.40
    assert row["closing_qty"] == 23 and row["closing_value"] == 55.2       # 23 x 2.40
    assert row["cost_consumed"] == round(row["opening_value"] + row["purchases"] - row["closing_value"], 2) == 16.8
    assert row["cost_consumed"] == round(row["issued"] + row["breakage_damage"] - row["count_adjustments"], 2)


def test_a_count_loss_is_costed_at_the_average_and_counts_as_consumption(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    receive(client, login, db, item, sup, 10, 3.00, "W-C1")
    count = client.post("/api/stock/counts", headers=login(SUP), json={"location_id": loc_id(db, "MK"), "lines": [{"item_id": item["id"], "counted_qty": 8}]}).json()
    assert client.post(f"/api/stock/counts/{count['id']}/post", headers=login(MGR), json={}).status_code == 200
    report = client.get(f"{URL}?location_id={loc_id(db, 'MK')}&date_from=2026-03-01&date_to=2026-03-31", headers=login(MGR)).json()
    row = next(r for r in report["rows"] if r["item_id"] == item["id"])
    assert row["count_adjustments"] == -6.0 and row["closing_value"] == 24.0 and row["cost_consumed"] == 6.0


def test_the_cost_report_is_in_the_records_and_needs_the_inventory_module(client, login, db, clock):
    item, sup = item_and_supplier(client, login, db)
    receive(client, login, db, item, sup, 10, 2.00, "W-X1")
    doc = client.get("/api/reports/records/stock_cost?date_from=2026-03-01&date_to=2026-03-31", headers=login(MGR)).json()
    group = next(g for g in doc["groups"] if "Main Kitchen" in g["title"])
    assert dict(group["totals"])["Purchases"] == "20.00" and ("Costing method", "Weighted average cost") in [tuple(m) for m in group["meta"]]
    for fmt in ("pdf", "xlsx", "csv"):
        assert client.get(f"/api/reports/records/stock_cost/export?fmt={fmt}&date_from=2026-03-01&date_to=2026-03-31", headers=login(MGR)).status_code == 200
    assert client.get(f"{URL}?location_id=1&date_from=2026-03-01&date_to=2026-03-31", headers=login("steward.mk@example.test")).status_code == 403
    assert client.get(f"{URL}?location_id=1&date_from=2026-03-31&date_to=2026-03-01", headers=login(MGR)).status_code == 400
