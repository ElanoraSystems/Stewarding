from sqlalchemy import select

from app.models import InventoryBalance, InventoryItem, Location, StockTransaction

MGR = "manager@example.test"
SUP = "sup.mk@example.test"
SUP_RB = "sup.rb@example.test"
STEWARD = "steward.mk@example.test"
STEWARD_RB = "steward.rb@example.test"


def loc_id(db, code):
    return db.scalar(select(Location.id).where(Location.code == code))


def item_id(db, code):
    return db.scalar(select(InventoryItem.id).where(InventoryItem.code == code))


def balance(db, code, location_code):
    db.expire_all()
    value = db.scalar(select(InventoryBalance.qty).where(
        InventoryBalance.item_id == item_id(db, code), InventoryBalance.location_id == loc_id(db, location_code)))
    return value or 0


def ledger_sum(db, code, location_code):
    db.expire_all()
    rows = db.scalars(select(StockTransaction.qty_delta).where(
        StockTransaction.item_id == item_id(db, code), StockTransaction.location_id == loc_id(db, location_code)))
    return sum(rows)
