"""Month-end closing balances, a rebuildable copy of the ledger total so reconciliation need not sum all history.

The ledger stays the single source of truth. A snapshot is checked against it, and a snapshot that differs is deleted
(with every later one) so reconciliation falls back to the full sum until the next run rebuilds it.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import Location, StockSnapshot, StockTransaction
from ..permissions import MANAGER
from .inventory import _month_bounds
from .notify import notify, recipients

MAX_BUILDS_PER_RUN = 12
VERIFY_LAST = 2


def _next_month(month: str) -> str:
    year, mon = (int(p) for p in month.split("-"))
    return f"{year + (mon == 12)}-{mon % 12 + 1:02d}"


def previous_snapshot_month(db: Session, location_id: int, month: str) -> str | None:
    """The latest month before `month` that has a snapshot for the location."""
    return db.scalar(select(func.max(StockSnapshot.month)).where(StockSnapshot.location_id == location_id, StockSnapshot.month < month))


def snapshot_quantities(db: Session, location_id: int, month: str) -> dict[int, int]:
    return dict(db.execute(select(StockSnapshot.item_id, StockSnapshot.qty).where(
        StockSnapshot.location_id == location_id, StockSnapshot.month == month)).all())


def ledger_closing(db: Session, location: Location, month: str) -> dict[int, int]:
    """The full sum of the ledger up to the end of the month, for every item that has moved."""
    _, end = _month_bounds(location.timezone, month)
    return dict(db.execute(select(StockTransaction.item_id, func.sum(StockTransaction.qty_delta)).where(
        StockTransaction.location_id == location.id, StockTransaction.occurred_at < end).group_by(StockTransaction.item_id)).all())


def build(db: Session, location: Location, month: str) -> int:
    """Stores the closing balances and values for the month, starting from the previous snapshot when there is one."""
    _, end = _month_bounds(location.timezone, month)
    base_month = previous_snapshot_month(db, location.id, month)
    totals: dict[int, int] = {}
    worth: dict[int, Decimal] = {}
    if base_month:
        for item_id, qty, value in db.execute(select(StockSnapshot.item_id, StockSnapshot.qty, StockSnapshot.value).where(
                StockSnapshot.location_id == location.id, StockSnapshot.month == base_month)):
            totals[item_id], worth[item_id] = qty, Decimal(str(value))
    stmt = select(StockTransaction.item_id, func.sum(StockTransaction.qty_delta),
                  func.sum(StockTransaction.qty_delta * func.coalesce(StockTransaction.unit_cost, 0))).where(
        StockTransaction.location_id == location.id, StockTransaction.occurred_at < end)
    if base_month:
        stmt = stmt.where(StockTransaction.occurred_at >= _month_bounds(location.timezone, base_month)[1])
    for item_id, total, value in db.execute(stmt.group_by(StockTransaction.item_id)):
        totals[item_id] = totals.get(item_id, 0) + total
        worth[item_id] = worth.get(item_id, Decimal(0)) + Decimal(str(value or 0))
    db.execute(delete(StockSnapshot).where(StockSnapshot.location_id == location.id, StockSnapshot.month == month))
    if totals:  # one batched insert, not a statement per row
        built_at = timeutil.utc_now()
        db.execute(insert(StockSnapshot), [{"location_id": location.id, "item_id": item_id, "month": month, "qty": int(qty),
                                            "value": worth.get(item_id, Decimal(0)), "built_at": built_at} for item_id, qty in totals.items()])
    return len(totals)


def differences(db: Session, location: Location, month: str) -> list[tuple[int, int, int]]:
    """(item, stored, actual) for every item whose snapshot differs from the full ledger sum."""
    stored, actual = snapshot_quantities(db, location.id, month), ledger_closing(db, location, month)
    return sorted((item, stored.get(item, 0), actual.get(item, 0)) for item in stored.keys() | actual.keys()
                  if stored.get(item, 0) != actual.get(item, 0))


def forget_from(db: Session, location_id: int, month: str | None = None) -> None:
    """Drops the snapshots of a location from `month` on, or all of them."""
    stmt = delete(StockSnapshot).where(StockSnapshot.location_id == location_id)
    if month:
        stmt = stmt.where(StockSnapshot.month >= month)
    db.execute(stmt)


def closed_months(db: Session, location: Location, now: datetime) -> list[str]:
    """Every month from the first movement up to the last month that has fully ended in the location's time zone."""
    first = db.scalar(select(func.min(StockTransaction.occurred_at)).where(StockTransaction.location_id == location.id))
    if first is None:
        return []
    today = timeutil.local_date(now, location.timezone)
    current = f"{today.year}-{today.month:02d}"
    month = f"{timeutil.local_date(first, location.timezone):%Y-%m}"
    out = []
    while month < current:
        out.append(month)
        month = _next_month(month)
    return out


def refresh(db: Session, now: datetime) -> dict[str, int]:
    """Builds the missing closed months (oldest first) and checks the newest snapshots; idempotent."""
    built = healed = 0
    for location in db.scalars(select(Location).where(Location.active.is_(True))):
        months = closed_months(db, location, now)
        have = {m for (m,) in db.execute(select(StockSnapshot.month).where(StockSnapshot.location_id == location.id).distinct())}
        for month in [m for m in months if m not in have][:MAX_BUILDS_PER_RUN]:
            build(db, location, month)
            built += 1
        for month in [m for m in months if m in have][-VERIFY_LAST:]:
            wrong = differences(db, location, month)
            if wrong:
                forget_from(db, location.id, month)
                healed += 1
                notify(db, recipients(db, None, MANAGER), "snapshot_mismatch",
                       f"Stock snapshot for {location.name} {month} did not match the ledger",
                       key=f"snapshot:{location.id}:{month}:{now.date().isoformat()}", priority="high", location_id=location.id,
                       body=f"{len(wrong)} item(s) differed. The snapshot was dropped and is rebuilt from the ledger.")
                break
    return {"built": built, "healed": healed}
