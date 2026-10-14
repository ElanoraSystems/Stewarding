import re
from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, permissions_of, require, scoped_locations
from ..models import (ApprovalRecord, InventoryBalance, InventoryCount, InventoryCountLine, InventoryItem,
                      InventoryTransfer, InventoryTransferLine, Location, User)
from ..pagination import row
from ..permissions import MANAGER
from ..services import metrics
from ..services.costing import cost_report
from ..services.inventory import StockError, post_txn, received_to_date, reconcile, variance_summary
from ..services.notify import notify, recipients
from .inventory import get_item_or_404

router = APIRouter(prefix="/api/stock", tags=["stock"])

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TRANSFER_FIELDS = ("id", "from_location_id", "to_location_id", "status", "requested_by", "requested_at", "decided_by",
                   "decided_at", "note")


class LineIn(BaseModel):
    item_id: int
    qty: int = Field(gt=0)


class TransferIn(BaseModel):
    from_location_id: int
    to_location_id: int
    lines: list[LineIn] = Field(min_length=1)
    note: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class CountLineIn(BaseModel):
    item_id: int
    counted_qty: int = Field(ge=0)


class CountIn(BaseModel):
    location_id: int
    lines: list[CountLineIn] = Field(min_length=1)


def _transfer_dict(db: Session, transfer: InventoryTransfer) -> dict:
    lines = db.scalars(select(InventoryTransferLine).where(InventoryTransferLine.transfer_id == transfer.id))
    return {**row(transfer, *TRANSFER_FIELDS), "lines": [row(ln, "item_id", "qty") for ln in lines]}


def _execute_transfer(db: Session, user: User, transfer: InventoryTransfer) -> None:
    for line in db.scalars(select(InventoryTransferLine).where(InventoryTransferLine.transfer_id == transfer.id)):
        item = db.get(InventoryItem, line.item_id)
        sent = post_txn(db, user, item, transfer.from_location_id, "transfer_out", line.qty, transfer.note,
                        "transfer", transfer.id)
        post_txn(db, user, item, transfer.to_location_id, "transfer_in", line.qty, transfer.note,
                 "transfer", transfer.id, unit_cost=sent.unit_cost)
    transfer.status = "completed"
    transfer.decided_by, transfer.decided_at = user.id, timeutil.utc_now()


@router.get("/locations")
def destinations(user: User = Depends(require("stock.transfer")), db: Session = Depends(get_db)):
    """Every active location, so a transfer can target one the caller is not assigned to."""
    return [row(loc, "id", "code", "name") for loc in db.scalars(
        select(Location).where(Location.active.is_(True)).order_by(Location.name))]


@router.post("/transfers", status_code=201)
def request_transfer(body: TransferIn, user: User = Depends(require("stock.transfer")), db: Session = Depends(get_db)):
    check_location(user, db, body.from_location_id)
    if not db.get(Location, body.to_location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destination location not found")
    if body.from_location_id == body.to_location_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Source and destination must differ")
    wanted: dict[int, int] = {}
    for line in body.lines:
        item = get_item_or_404(db, line.item_id)
        if not item.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{item.name} is retired")
        wanted[item.id] = wanted.get(item.id, 0) + line.qty
        on_hand = db.scalar(select(InventoryBalance.qty).where(InventoryBalance.item_id == item.id, InventoryBalance.location_id == body.from_location_id)) or 0
        if wanted[item.id] > on_hand:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Only {on_hand} of {item.name} are in stock at the source location")
    transfer = InventoryTransfer(from_location_id=body.from_location_id, to_location_id=body.to_location_id,
                                 requested_by=user.id, requested_at=timeutil.utc_now(), note=body.note)
    db.add(transfer)
    db.flush()
    db.add_all(InventoryTransferLine(transfer_id=transfer.id, item_id=ln.item_id, qty=ln.qty) for ln in body.lines)
    db.flush()
    if "stock.approve" in permissions_of(user):
        try:
            _execute_transfer(db, user, transfer)
        except StockError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        db.add(ApprovalRecord(subject_type="transfer", subject_id=transfer.id, decision="approved", decided_by=user.id,
                              reason="Requested by approver"))
    else:
        notify(db, recipients(db, None, MANAGER), "transfer_pending", "Stock transfer awaiting approval",
               key=f"transfer:{transfer.id}", priority="high", location_id=body.from_location_id,
               link="/stock-movements")
    audit(db, user, "stock.transfer_request", "inventory_transfer", transfer.id, None, body.model_dump(mode="json"))
    db.commit()
    return _transfer_dict(db, transfer)


@router.get("/transfers")
def list_transfers(transfer_status: str | None = None, user: User = Depends(require("inventory.module")),
                   db: Session = Depends(get_db)):
    stmt = select(InventoryTransfer)
    scope = scoped_locations(user, db)
    if scope is not None:
        stmt = stmt.where(or_(InventoryTransfer.from_location_id.in_(scope), InventoryTransfer.to_location_id.in_(scope)))
    if transfer_status:
        stmt = stmt.where(InventoryTransfer.status == transfer_status)
    return [_transfer_dict(db, t) for t in db.scalars(stmt.order_by(InventoryTransfer.id.desc()).limit(100))]


@router.post("/transfers/{transfer_id}/decision")
def decide_transfer(transfer_id: int, body: DecisionIn, user: User = Depends(require("stock.approve")),
                    db: Session = Depends(get_db)):
    transfer = db.get(InventoryTransfer, transfer_id)
    if not transfer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transfer not found")
    if transfer.status != "requested":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Transfer is already {transfer.status}")
    if transfer.requested_by == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot approve your own request")
    if body.approve:
        try:
            _execute_transfer(db, user, transfer)
        except StockError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    else:
        transfer.status, transfer.decided_by, transfer.decided_at = "rejected", user.id, timeutil.utc_now()
        notify(db, [transfer.requested_by], "transfer_rejected", "Stock transfer rejected",
               key=f"transfer_rejected:{transfer.id}", body=body.note, location_id=transfer.from_location_id)
    db.add(ApprovalRecord(subject_type="transfer", subject_id=transfer.id,
                          decision="approved" if body.approve else "rejected", decided_by=user.id, reason=body.note))
    audit(db, user, "stock.transfer_decision", "inventory_transfer", transfer.id, {"status": "requested"},
          {"status": transfer.status})
    db.commit()
    return _transfer_dict(db, transfer)


def _count_dict(db: Session, count: InventoryCount) -> dict:
    lines = db.scalars(select(InventoryCountLine).where(InventoryCountLine.count_id == count.id))
    return {**row(count, "id", "location_id", "counted_at", "counted_by", "status", "month"),
            "lines": [{**row(ln, "item_id", "system_qty", "counted_qty", "adjustment_txn_id"),
                       "variance": ln.counted_qty - ln.system_qty} for ln in lines]}


@router.post("/counts", status_code=201)
def create_count(body: CountIn, user: User = Depends(require("inventory.count")), db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    location = db.get(Location, body.location_id)
    if len({ln.item_id for ln in body.lines}) != len(body.lines):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each item can be counted once")
    # A count can find less than the book figure, never more than what was received into this location.
    received = received_to_date(db, location.id, [ln.item_id for ln in body.lines])
    items = {}
    for ln in body.lines:
        items[ln.item_id] = item = get_item_or_404(db, ln.item_id)
        if ln.counted_qty > received.get(item.id, 0):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"{item.name}: counted {ln.counted_qty} is more than the {received.get(item.id, 0)} received "
                                "into this location. Receive the missing stock first.")
    now = timeutil.utc_now()
    count = InventoryCount(location_id=location.id, counted_by=user.id, counted_at=now,
                           month=timeutil.to_local(now, location.timezone).strftime("%Y-%m"))
    db.add(count)
    db.flush()
    for ln in body.lines:
        item = items[ln.item_id]
        balance = db.get(InventoryBalance, (item.id, location.id))
        db.add(InventoryCountLine(count_id=count.id, item_id=item.id, system_qty=balance.qty if balance else 0,
                                  counted_qty=ln.counted_qty))
    db.commit()
    return _count_dict(db, count)


@router.get("/counts")
def list_counts(location_id: int | None = None, user: User = Depends(require("inventory.count")),
                db: Session = Depends(get_db)):
    stmt = select(InventoryCount)
    scope = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(InventoryCount.location_id == location_id)
    elif scope is not None:
        stmt = stmt.where(InventoryCount.location_id.in_(scope))
    return [_count_dict(db, c) for c in db.scalars(stmt.order_by(InventoryCount.id.desc()).limit(50))]


@router.post("/counts/{count_id}/post")
def post_count(count_id: int, user: User = Depends(require("inventory.count")), db: Session = Depends(get_db)):
    count = db.get(InventoryCount, count_id)
    if not count:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Count not found")
    check_location(user, db, count.location_id)
    if count.status == "posted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Count was already posted")
    lines = db.scalars(select(InventoryCountLine).where(InventoryCountLine.count_id == count.id)).all()
    variances = [ln for ln in lines if ln.counted_qty != ln.system_qty]
    if variances and "stock.approve" not in permissions_of(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a manager can post a count that has variances")
    for ln in variances:
        item = db.get(InventoryItem, ln.item_id)
        txn = post_txn(db, user, item, count.location_id, "adjustment", ln.counted_qty - ln.system_qty,
                       f"Physical count #{count.id} variance", "count", count.id, allow_negative=True)
        ln.adjustment_txn_id = txn.id
    count.status = "posted"
    audit(db, user, "stock.count_post", "inventory_count", count.id, None,
          {"variances": [{"item_id": ln.item_id, "delta": ln.counted_qty - ln.system_qty} for ln in variances]})
    db.commit()
    return _count_dict(db, count)


@router.get("/insights")
def insights(location_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
             user: User = Depends(require("inventory.module")), db: Session = Depends(get_db)):
    """Stock in and out, breakage and transfers for charts; the last 30 days unless dates are given."""
    now = timeutil.utc_now()
    if location_id is not None:
        check_location(user, db, location_id)
    scope = scoped_locations(user, db)
    first = metrics.windows_by(db, now, scope, location_id, lambda t: (t, t))
    if not first:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No locations in scope")
    day_to = date_to or first[0].today
    day_from = date_from or day_to - timedelta(days=29)
    try:
        wins = metrics.windows(db, now, scope, location_id, day_from, day_to)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return metrics.stock_insights(db, wins, day_from, day_to)


@router.get("/cost-report")
def stock_cost(location_id: int, date_from: date, date_to: date,
               user: User = Depends(require("inventory.module")), db: Session = Depends(get_db)):
    """Opening value, purchases, closing value and cost consumed for a period, at weighted average cost."""
    if date_to < date_from or (date_to - date_from).days >= 731:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a period of at most two years that ends after it starts")
    check_location(user, db, location_id)
    location = db.get(Location, location_id)
    start = timeutil.local_to_utc(date_from, time(0), location.timezone)
    end = timeutil.local_to_utc(date_to + timedelta(days=1), time(0), location.timezone)
    return {"location_id": location_id, "from": date_from.isoformat(), "to": date_to.isoformat(), **cost_report(db, location_id, start, end)}


@router.get("/reconciliation")
def reconciliation(location_id: int, month: str,
                   user: User = Depends(require("inventory.module")), db: Session = Depends(get_db)):
    if not MONTH_RE.match(month):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "month must be YYYY-MM")
    check_location(user, db, location_id)
    rows = reconcile(db, db.get(Location, location_id), month)
    return {"location_id": location_id, "month": month, "rows": rows, "variance": variance_summary(rows),
            "total_closing": sum(r["closing"] for r in rows)}
