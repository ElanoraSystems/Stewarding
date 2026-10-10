from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, permissions_of, require, scoped_locations
from ..models import ApprovalRecord, BreakageIncident, Employee, InventoryItem, Shift, User
from ..pagination import paginate, row
from ..permissions import MANAGER, SUPERVISOR
from ..services.inventory import post_txn
from ..services.notify import notify, recipients
from ..services.settings import get_setting
from .inventory import get_item_or_404
from .uploads import is_valid_evidence

router = APIRouter(prefix="/api/breakage", tags=["breakage"])

FIELDS = ("id", "code", "occurred_at", "location_id", "item_id", "qty", "incident_type", "reason", "description",
          "shift_id", "reported_by", "photo_path", "est_cost", "status", "reviewed_by", "reviewed_at", "approved_by",
          "approved_at", "preventive_action", "transaction_id")
TXN_TYPE = {"breakage": "breakage", "damage": "damage", "missing": "adjustment", "written_off": "adjustment"}


class ReportIn(BaseModel):
    location_id: int
    item_id: int
    qty: int = Field(gt=0, le=10000)
    incident_type: Literal["breakage", "damage", "missing", "written_off"]
    reason: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    shift_id: int | None = None
    photo_path: str | None = None
    est_cost: Decimal | None = Field(default=None, ge=0)


class ReviewIn(BaseModel):
    qty: int = Field(gt=0, le=10000)
    reason: str | None = Field(default=None, max_length=500)
    preventive_action: str | None = Field(default=None, max_length=1000)


class RejectIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class ApproveIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)


def _get(db: Session, user: User, incident_id: int) -> BreakageIncident:
    incident = db.get(BreakageIncident, incident_id)
    if not incident:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    check_location(user, db, incident.location_id)
    return incident


def _serialize(incident: BreakageIncident, names: dict[int, str] | None = None) -> dict:
    out = row(incident, *FIELDS)
    if names is not None:
        out["reported_by_name"] = names.get(incident.reported_by)
    return out


def _needs_approval(db: Session, qty: int, cost) -> bool:
    over_qty = qty >= get_setting(db, "breakage.approval_qty")
    over_cost = cost is not None and cost >= get_setting(db, "breakage.approval_cost")
    return over_qty or over_cost


def _deduct(db: Session, user: User, incident: BreakageIncident) -> None:
    """Posts the single linked stock transaction; the unique transaction_id prevents a second deduction."""
    if incident.transaction_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Stock was already deducted for this incident")
    item = db.get(InventoryItem, incident.item_id)
    reason = f"{incident.code}: {incident.incident_type}" + (f" - {incident.reason}" if incident.reason else "")
    txn_type = TXN_TYPE[incident.incident_type]
    qty = -incident.qty if txn_type == "adjustment" else incident.qty
    txn = post_txn(db, user, item, incident.location_id, txn_type, qty, reason, "breakage", incident.id,
                   allow_negative=True)
    incident.transaction_id = txn.id


@router.post("", status_code=201)
def report(body: ReportIn, user: User = Depends(require("breakage.report")), db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    item = get_item_or_404(db, body.item_id)
    if body.shift_id is not None and not db.get(Shift, body.shift_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown shift")
    if body.photo_path and not is_valid_evidence(body.photo_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown photo file")
    now = timeutil.utc_now()
    cost = body.est_cost if body.est_cost is not None else (item.unit_cost * body.qty if item.unit_cost else None)
    incident = BreakageIncident(code="PENDING", occurred_at=now, reported_by=user.id, est_cost=cost,
                                **body.model_dump(exclude={"est_cost"}))
    db.add(incident)
    db.flush()
    incident.code = f"BRK-{now:%Y%m}-{incident.id:04d}"
    notify(db, recipients(db, incident.location_id, SUPERVISOR, MANAGER), "breakage_review",
           f"Breakage to review: {body.qty} x {item.name}", key=f"brk_review:{incident.id}", priority="high",
           location_id=incident.location_id, link="/breakage")
    db.commit()
    return _serialize(incident)


@router.get("/mine")
def mine(user: User = Depends(require("breakage.report")), db: Session = Depends(get_db)):
    stmt = select(BreakageIncident).where(BreakageIncident.reported_by == user.id).order_by(BreakageIncident.id.desc())
    return [_serialize(i) for i in db.scalars(stmt.limit(50))]


@router.get("")
def list_incidents(location_id: int | None = None, incident_status: str | None = None, incident_type: str | None = None,
                   item_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                   page: int = 1, size: int = 25, user: User = Depends(require("breakage.view")),
                   db: Session = Depends(get_db)):
    stmt = select(BreakageIncident)
    scope = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(BreakageIncident.location_id == location_id)
    elif scope is not None:
        stmt = stmt.where(BreakageIncident.location_id.in_(scope))
    if incident_status:
        stmt = stmt.where(BreakageIncident.status == incident_status)
    if incident_type:
        stmt = stmt.where(BreakageIncident.incident_type == incident_type)
    if item_id is not None:
        stmt = stmt.where(BreakageIncident.item_id == item_id)
    if date_from:
        stmt = stmt.where(BreakageIncident.occurred_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(BreakageIncident.occurred_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    total, rows = paginate(db, stmt.order_by(BreakageIncident.id.desc()), page, size)
    incidents = [r[0] for r in rows]
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    return {"total": total, "items": [_serialize(i, names) for i in incidents]}


@router.post("/{incident_id}/review")
def review(incident_id: int, body: ReviewIn, user: User = Depends(require("breakage.review")),
           db: Session = Depends(get_db)):
    incident = _get(db, user, incident_id)
    if incident.status != "reported":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Incident is already {incident.status}")
    if incident.reported_by == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot review an incident you reported")
    now = timeutil.utc_now()
    item = db.get(InventoryItem, incident.item_id)
    incident.qty = body.qty
    incident.reason = body.reason or incident.reason
    incident.preventive_action = body.preventive_action
    if item.unit_cost is not None:
        incident.est_cost = item.unit_cost * body.qty
    incident.reviewed_by, incident.reviewed_at = user.id, now
    if _needs_approval(db, incident.qty, incident.est_cost):
        incident.status = "pending_approval"
        notify(db, recipients(db, None, MANAGER), "breakage_approval", f"Approval needed: {incident.code}",
               key=f"brk_approve:{incident.id}", priority="high", location_id=incident.location_id,
               link="/breakage", requires_ack=True)
    else:
        _deduct(db, user, incident)
        incident.status, incident.approved_by, incident.approved_at = "approved", user.id, now
        db.add(ApprovalRecord(subject_type="breakage", subject_id=incident.id, decision="approved",
                              decided_by=user.id, reason="Within approval threshold"))
    audit(db, user, "breakage.review", "breakage_incident", incident.id, None, {"qty": incident.qty,
                                                                                 "status": incident.status})
    db.commit()
    return _serialize(incident)


@router.post("/{incident_id}/approve")
def approve(incident_id: int, body: ApproveIn, user: User = Depends(require("breakage.approve")),
            db: Session = Depends(get_db)):
    incident = _get(db, user, incident_id)
    if incident.status != "pending_approval":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Incident is {incident.status}, not awaiting approval")
    if incident.reported_by == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot approve an incident you reported")
    _deduct(db, user, incident)
    incident.status, incident.approved_by, incident.approved_at = "approved", user.id, timeutil.utc_now()
    db.add(ApprovalRecord(subject_type="breakage", subject_id=incident.id, decision="approved", decided_by=user.id,
                          reason=body.note))
    audit(db, user, "breakage.approve", "breakage_incident", incident.id, None, {"transaction_id": incident.transaction_id})
    db.commit()
    return _serialize(incident)


@router.post("/{incident_id}/reject")
def reject(incident_id: int, body: RejectIn, user: User = Depends(require("breakage.review")),
           db: Session = Depends(get_db)):
    incident = _get(db, user, incident_id)
    if incident.status not in ("reported", "pending_approval"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Incident is already {incident.status}")
    if incident.status == "pending_approval" and "breakage.approve" not in permissions_of(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a manager can reject an incident awaiting approval")
    incident.status, incident.reviewed_by, incident.reviewed_at = "rejected", user.id, timeutil.utc_now()
    db.add(ApprovalRecord(subject_type="breakage", subject_id=incident.id, decision="rejected", decided_by=user.id,
                          reason=body.reason))
    audit(db, user, "breakage.reject", "breakage_incident", incident.id, None, {"reason": body.reason})
    db.commit()
    return _serialize(incident)
