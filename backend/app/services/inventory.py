from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import (InventoryBalance, InventoryCount, InventoryCountLine, InventoryItem, Location, StockTransaction,
                      User)
from ..permissions import MANAGER, SUPERVISOR
from .notify import notify, recipients

# Direction of each transaction type; adjustments carry their own sign.
SIGN = {"opening": 1, "receipt": 1, "return": 1, "transfer_in": 1, "issue": -1, "damage": -1, "breakage": -1,
        "transfer_out": -1}
OUTFLOW_TYPES = ("issue", "damage", "breakage")


class StockError(Exception):
    pass


def post_txn(db: Session, user: User, item: InventoryItem, location_id: int, txn_type: str, qty: int,
             reason: str | None = None, ref_type: str | None = None, ref_id: int | None = None,
             allow_negative: bool = False) -> StockTransaction:
    """Appends one immutable ledger row and moves the balance in the caller's transaction."""
    delta = qty if txn_type == "adjustment" else SIGN[txn_type] * abs(qty)
    if delta == 0:
        raise StockError("Quantity must not be zero")
    balance = db.get(InventoryBalance, (item.id, location_id), with_for_update=True)
    if balance is None:
        balance = InventoryBalance(item_id=item.id, location_id=location_id, qty=0)
        db.add(balance)
        db.flush()
    if balance.qty + delta < 0 and not allow_negative:
        raise StockError(f"Insufficient stock of {item.name}: {balance.qty} available")
    balance.qty += delta
    txn = StockTransaction(item_id=item.id, location_id=location_id, txn_type=txn_type, qty_delta=delta,
                           occurred_at=timeutil.utc_now(), user_id=user.id, reason=reason, ref_type=ref_type,
                           ref_id=ref_id)
    db.add(txn)
    db.flush()
    if delta < 0 and balance.qty < item.min_level:
        notify(db, recipients(db, location_id, SUPERVISOR, MANAGER), "low_stock",
               f"Low stock: {item.name} ({balance.qty} left, minimum {item.min_level})",
               key=f"low:{item.id}:{location_id}:{timeutil.utc_now().date().isoformat()}", priority="high",
               location_id=location_id, link=f"/{item.kind}")
    return txn


def _month_bounds(tz: str, month: str) -> tuple[datetime, datetime]:
    year, mon = (int(p) for p in month.split("-"))
    first = date(year, mon, 1)
    following = date(year + (mon == 12), mon % 12 + 1, 1)
    return timeutil.local_to_utc(first, time(0), tz), timeutil.local_to_utc(following, time(0), tz)


def reconcile(db: Session, location: Location, kind: str, month: str) -> list[dict]:
    """Per item: opening + movements = closing, plus the latest posted physical count in the month."""
    start, end = _month_bounds(location.timezone, month)
    items = db.scalars(select(InventoryItem).where(InventoryItem.kind == kind).order_by(InventoryItem.code)).all()
    txns = db.scalars(select(StockTransaction).where(StockTransaction.location_id == location.id,
                                                     StockTransaction.occurred_at < end)).all()
    counts = db.execute(
        select(InventoryCountLine, InventoryCount).join(InventoryCount, InventoryCount.id == InventoryCountLine.count_id)
        .where(InventoryCount.location_id == location.id, InventoryCount.status == "posted",
               InventoryCount.counted_at >= start, InventoryCount.counted_at < end)
        .order_by(InventoryCount.counted_at)).all()
    last_count = {line.item_id: line for line, _ in counts}
    rows = []
    for item in items:
        mine = [t for t in txns if t.item_id == item.id]
        before = sum(t.qty_delta for t in mine if t.occurred_at < start)
        month_txns = [t for t in mine if t.occurred_at >= start]
        total = lambda *types: sum(t.qty_delta for t in month_txns if t.txn_type in types)  # noqa: E731
        movements = {
            "opening_stock": total("opening"), "receipts": total("receipt"), "returns": total("return"),
            "issues": total("issue"), "breakage_damage": total("breakage", "damage"),
            "transfers_in": total("transfer_in"), "transfers_out": total("transfer_out"),
            "adjustments": total("adjustment"),
        }
        closing = before + sum(movements.values())
        if not mine and item.id not in last_count:
            continue
        line = last_count.get(item.id)
        rows.append({
            "item_id": item.id, "code": item.code, "name": item.name, "opening": before, **movements,
            "closing": closing, "counted_qty": line.counted_qty if line else None,
            "count_variance": line.counted_qty - line.system_qty if line else None,
            "value": float(closing * item.unit_cost) if item.unit_cost is not None else None,
        })
    return rows


def balance_matches_ledger(db: Session, item_id: int, location_id: int) -> bool:
    ledger = db.scalar(select(func.coalesce(func.sum(StockTransaction.qty_delta), 0)).where(
        StockTransaction.item_id == item_id, StockTransaction.location_id == location_id))
    balance = db.get(InventoryBalance, (item_id, location_id))
    return ledger == (balance.qty if balance else 0)
