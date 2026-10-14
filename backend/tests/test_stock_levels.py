from sqlalchemy import select

from app.models import AuditLog, InventoryLevel, Notification

from .helpers import MGR, STEWARD, SUP, item_id, loc_id


def put_level(client, h, db, code, place, value):
    return client.put(f"/api/inventory/items/{item_id(db, code)}/levels/{loc_id(db, place)}", headers=h, json={"min_level": value})


def listed(client, h, db, code, place=None):
    query = f"?location_id={loc_id(db, place)}" if place else ""
    return next(i for i in client.get(f"/api/inventory/items{query}", headers=h).json()["items"] if i["code"] == code)


def test_a_location_minimum_makes_that_location_short_and_names_who_can_spare(client, login, db, clock):
    sup = login(SUP)
    assert put_level(client, sup, db, "PL-002", "MK", 150).status_code == 200      # 120 held, 80 more wanted up to the target of 200
    found = client.get("/api/inventory/shortages", headers=sup).json()
    row = next(r for r in found["items"] if r["code"] == "PL-002")
    assert (row["location"], row["qty"], row["minimum"]) == ("Main Kitchen", 120, 150)
    assert [(d["location"], d["spare"]) for d in row["donors"]] == [("Banquet Hall", 60)]
    assert row["suggested_qty"] == 60
    assert found["total"] == len(found["items"])
    here = client.get(f"/api/inventory/shortages?location_id={loc_id(db, 'MK')}", headers=sup).json()["items"]
    assert [d["location"] for d in next(r for r in here if r["code"] == "PL-002")["donors"]] == ["Banquet Hall"]   # a chosen location still sees who can spare


def test_the_item_list_shows_the_shortage_at_a_location_and_not_elsewhere(client, login, db, clock):
    m = login(MGR)
    assert not listed(client, m, db, "PL-002")["low"]
    put_level(client, m, db, "PL-002", "MK", 150)
    everywhere = listed(client, m, db, "PL-002")
    assert everywhere["low"] and [s["location_id"] for s in everywhere["short_at"]] == [loc_id(db, "MK")]
    assert listed(client, m, db, "PL-002", "MK")["minimum"] == 150
    assert not listed(client, m, db, "PL-002", "BQ")["low"] and listed(client, m, db, "PL-002", "BQ")["minimum"] == 40
    low_codes = {i["code"] for i in client.get("/api/inventory/items?low_only=true", headers=m).json()["items"]}
    assert "PL-002" in low_codes


def test_going_back_to_the_item_minimum_clears_the_shortage(client, login, db, clock):
    m = login(MGR)
    put_level(client, m, db, "PL-002", "MK", 150)
    assert put_level(client, m, db, "PL-002", "MK", None).json()["override"] is False
    assert db.scalar(select(InventoryLevel)) is None
    assert not any(r["code"] == "PL-002" for r in client.get("/api/inventory/shortages", headers=m).json()["items"])


def test_only_people_who_count_stock_in_their_own_locations_may_change_a_minimum(client, login, db, clock):
    assert put_level(client, login(STEWARD), db, "PL-002", "MK", 10).status_code == 403
    assert put_level(client, login(SUP), db, "PL-002", "RB", 10).status_code == 403
    assert put_level(client, login(SUP), db, "PL-002", "MK", 250).status_code == 400   # above the target of 200
    assert db.scalar(select(InventoryLevel)) is None


def test_a_change_is_audited_and_the_low_stock_alert_uses_the_location_minimum(client, login, db, clock):
    sup = login(SUP)
    put_level(client, sup, db, "PL-002", "MK", 150)
    assert db.scalar(select(AuditLog).where(AuditLog.action == "inventory.level_update")) is not None
    issued = client.post("/api/inventory/transactions", headers=sup, json={
        "item_id": item_id(db, "PL-002"), "location_id": loc_id(db, "MK"), "txn_type": "issue", "qty": 1, "reason": "Service"})
    assert issued.status_code == 201
    alert = db.scalars(select(Notification).where(Notification.kind == "low_stock")).first()
    assert alert and "119 left, minimum 150" in alert.title


def test_location_stock_lists_every_item_and_prices_the_ones_with_no_average_yet(client, login, db, clock):
    rows = {r["item_id"]: r for r in client.get(f"/api/stock/location-stock?location_id={loc_id(db, 'RB')}", headers=login(MGR)).json()}
    knife = rows[item_id(db, "KN-001")]                       # the Rooftop Bar has never held a knife
    assert knife["qty"] == 0 and knife["avg_cost"] == 22.0    # falls back to the item's own cost, as the breakage report does
    assert rows[item_id(db, "PL-001")]["qty"] == 40
