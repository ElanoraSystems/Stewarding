from collections import deque
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import Lot, LotLink, ReadingLot, ShelfLifeRule

GROUPS = {"poultry": ("Poultry", "POU"), "red_meat": ("Red meat", "RED"), "seafood": ("Seafood", "SEA"),
          "dairy": ("Dairy", "DAI"), "eggs": ("Eggs", "EGG"), "other": ("Other", "OTH")}
CONDITIONS = {"chilled_raw": "Chilled, raw", "vacuum_chilled": "Vacuum packed, chilled", "frozen": "Frozen",
              "thawed": "Thawed", "cooked_chilled": "Cooked, chilled"}
STATUSES = ("active", "used_up", "discarded", "on_hold")


class LotError(Exception):
    """A lot cannot be made or used as asked; the message says why in words for the person."""


def shelf_hours(db: Session, group: str, condition: str) -> int | None:
    return db.scalar(select(ShelfLifeRule.hours).where(ShelfLifeRule.food_group == group, ShelfLifeRule.condition == condition))


def use_by_for(db: Session, group: str, condition: str, start: datetime, expiry_on: date | None, tz: str, rule_required: bool) -> datetime | None:
    """The earlier of the supplier's expiry (end of that day) and the shelf-life rule counted from `start`."""
    hours = shelf_hours(db, group, condition)
    if hours is None and rule_required:
        raise LotError(f"No shelf-life rule for {GROUPS[group][0]} ({CONDITIONS[condition]}). A manager sets it under Food Traceability > Shelf life")
    options = []
    if hours is not None:
        options.append(start + timedelta(hours=hours))
    if expiry_on:
        options.append(timeutil.local_to_utc(expiry_on + timedelta(days=1), time(0), tz))
    return min(options) if options else None


def _taken(db: Session, code: str) -> bool:
    return db.scalar(select(Lot.id).where(Lot.code == code)) is not None


def new_code(db: Session, group: str, day: date) -> str:
    """GROUP-yymmdd-nn, numbered within the group and day."""
    prefix = f"{GROUPS[group][1]}-{day:%y%m%d}-"
    number = (db.scalar(select(func.count()).select_from(Lot).where(Lot.code.like(f"{prefix}%"), Lot.kind == "received")) or 0) + 1
    while _taken(db, f"{prefix}{number:02d}"):
        number += 1
    return f"{prefix}{number:02d}"


def child_code(db: Session, parent: Lot) -> str:
    """The parent's code with a running number, so the family is visible on the label."""
    number = (db.scalar(select(func.count()).select_from(LotLink).where(LotLink.parent_id == parent.id)) or 0) + 1
    while _taken(db, f"{parent.code}-{number}"):
        number += 1
    return f"{parent.code}-{number}"


def _walk(db: Session, start: int, towards_parents: bool) -> list[Lot]:
    seen: dict[int, Lot] = {}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        column, other = (LotLink.child_id, LotLink.parent_id) if towards_parents else (LotLink.parent_id, LotLink.child_id)
        for lot in db.scalars(select(Lot).join(LotLink, other == Lot.id).where(column == current).order_by(Lot.id)):
            if lot.id not in seen:
                seen[lot.id] = lot
                queue.append(lot.id)
    return list(seen.values())


def ancestors(db: Session, lot_id: int) -> list[Lot]:
    """Every lot this one came from, oldest first."""
    return sorted(_walk(db, lot_id, True), key=lambda lot: lot.id)


def descendants(db: Session, lot_id: int) -> list[Lot]:
    """Every lot made from this one, however many splits away."""
    return sorted(_walk(db, lot_id, False), key=lambda lot: lot.id)


def readings_of(db: Session, lot_ids: list[int]) -> dict[int, list[int]]:
    """Reading ids per lot, for the checks (cooking, chilling) that named the lot."""
    out: dict[int, list[int]] = {i: [] for i in lot_ids}
    for lot_id, reading_id in db.execute(select(ReadingLot.lot_id, ReadingLot.reading_id).where(ReadingLot.lot_id.in_(lot_ids))):
        out[lot_id].append(reading_id)
    return out


def usable(lot: Lot, now: datetime) -> str | None:
    """Why a lot may not go into a check or a split, or None when it may."""
    if lot.status == "on_hold":
        return f"{lot.code} is on hold"
    if lot.status != "active":
        return f"{lot.code} is {lot.status.replace('_', ' ')}"
    if lot.use_by and lot.use_by < now:
        return f"{lot.code} is past its use-by date"
    return None
