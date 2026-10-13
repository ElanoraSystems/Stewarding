from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy import case, func, select
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


def norm(text: str) -> str:
    """Case- and spacing-insensitive key used to stop near-duplicate names."""
    return " ".join(text.lower().split())


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
               location_id=location_id, link="/inventory")
    return txn


def _month_bounds(tz: str, month: str) -> tuple[datetime, datetime]:
    year, mon = (int(p) for p in month.split("-"))
    first = date(year, mon, 1)
    following = date(year + (mon == 12), mon % 12 + 1, 1)
    return timeutil.local_to_utc(first, time(0), tz), timeutil.local_to_utc(following, time(0), tz)


def received_to_date(db: Session, location_id: int, item_ids: list[int]) -> dict[int, int]:
    """Everything that ever came into a location for each item: opening stock, receipts, returns, transfers in, increases."""
    if not item_ids:
        return {}
    rows = db.execute(select(StockTransaction.item_id, func.sum(StockTransaction.qty_delta)).where(
        StockTransaction.location_id == location_id, StockTransaction.qty_delta > 0,
        StockTransaction.item_id.in_(item_ids)).group_by(StockTransaction.item_id)).all()
    return {item_id: int(total) for item_id, total in rows}


def reconcile(db: Session, location: Location, month: str) -> list[dict]:
    """Per item: opening + movements = closing, plus the latest posted physical count in the month.

    The ledger is summed by the database, grouped by item, movement type and before or inside the month, so the
    work is one pass over the rows instead of a scan of every movement for every item.
    """
    start, end = _month_bounds(location.timezone, month)
    items = db.scalars(select(InventoryItem).order_by(InventoryItem.code)).all()
    in_month = case((StockTransaction.occurred_at >= start, 1), else_=0)
    sums = db.execute(
        select(StockTransaction.item_id, StockTransaction.txn_type, in_month.label("in_month"), func.sum(StockTransaction.qty_delta))
        .where(StockTransaction.location_id == location.id, StockTransaction.occurred_at < end)
        .group_by(StockTransaction.item_id, StockTransaction.txn_type, in_month)).all()
    before: dict[int, int] = defaultdict(int)
    during: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item_id, txn_type, inside, total in sums:
        if inside:
            during[item_id][txn_type] += total
        else:
            before[item_id] += total
    moved = set(before) | set(during)
    counts = db.execute(
        select(InventoryCountLine, InventoryCount).join(InventoryCount, InventoryCount.id == InventoryCountLine.count_id)
        .where(InventoryCount.location_id == location.id, InventoryCount.status == "posted",
               InventoryCount.counted_at >= start, InventoryCount.counted_at < end)
        .order_by(InventoryCount.counted_at)).all()
    last_count = {line.item_id: line for line, _ in counts}
    rows = []
    for item in items:
        if item.id not in moved and item.id not in last_count:
            continue
        mine = during[item.id]
        movements = {
            "opening_stock": mine["opening"], "receipts": mine["receipt"], "returns": mine["return"],
            "issues": mine["issue"], "breakage_damage": mine["breakage"] + mine["damage"],
            "transfers_in": mine["transfer_in"], "transfers_out": mine["transfer_out"],
            "adjustments": mine["adjustment"],
        }
        closing = before[item.id] + sum(movements.values())
        line = last_count.get(item.id)
        variance = line.counted_qty - line.system_qty if line else None
        cost = float(item.unit_cost) if item.unit_cost is not None else None
        rows.append({
            "item_id": item.id, "code": item.code, "name": item.name, "opening": before[item.id], **movements,
            "closing": closing, "counted_qty": line.counted_qty if line else None,
            "count_variance": variance, "variance_value": round(variance * cost, 2) if variance and cost is not None else None,
            "value": float(closing * item.unit_cost) if item.unit_cost is not None else None,
        })
    return rows


def variance_summary(rows: list[dict]) -> dict:
    """Shortages and surpluses found by the month's posted counts, in units and in money."""
    short = [r for r in rows if r["count_variance"] and r["count_variance"] < 0]
    over = [r for r in rows if r["count_variance"] and r["count_variance"] > 0]
    return {"counted_items": sum(1 for r in rows if r["counted_qty"] is not None), "shortage_items": len(short),
            "surplus_items": len(over), "shortage_units": -sum(r["count_variance"] for r in short),
            "surplus_units": sum(r["count_variance"] for r in over),
            "net_value": round(sum(r["variance_value"] or 0 for r in rows), 2)}


def balance_matches_ledger(db: Session, item_id: int, location_id: int) -> bool:
    ledger = db.scalar(select(func.coalesce(func.sum(StockTransaction.qty_delta), 0)).where(
        StockTransaction.item_id == item_id, StockTransaction.location_id == location_id))
    balance = db.get(InventoryBalance, (item_id, location_id))
    return ledger == (balance.qty if balance else 0)
