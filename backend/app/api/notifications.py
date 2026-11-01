from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import Session

from .. import timeutil
from ..db import get_db
from ..deps import check_location, permissions_of, require, scoped_locations
from ..models import Notification, User
from ..pagination import paginate, row
from .dashboard import CATEGORY_SECTION, _sections
from ..services.approvals import record_decision
from ..services.summary import grouped, pending_items
from ..services.visibility import hidden_templates

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

PENDING_LIST = 200  # the totals count everything; the list shows the most urgent

FIELDS = ("id", "kind", "priority", "title", "body", "location_id", "link", "due_at", "created_at", "read_at",
          "requires_ack", "acknowledged_at", "resolved_at")


def _serialize(n: Notification) -> dict:
    out = row(n, *FIELDS)
    # critical alerts stay open until acknowledged or the underlying issue is resolved; reading does not close them
    out["action_needed"] = n.requires_ack and n.acknowledged_at is None and n.resolved_at is None
    return out


def _mine(db: Session, user: User, notification_id: int) -> Notification:
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return n


@router.get("")
def list_notifications(unread: bool = False, priority: str | None = None, page: int = 1, size: int = 25,
                       user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    if priority:
        stmt = stmt.where(Notification.priority == priority)
    pinned = case((Notification.requires_ack.is_(True) & Notification.acknowledged_at.is_(None)
                   & Notification.resolved_at.is_(None), 0), else_=1)
    total, rows = paginate(db, stmt.order_by(pinned, Notification.created_at.desc(), Notification.id.desc()), page, size)
    unread_count = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)))
    return {"total": total, "unread": unread_count, "items": [_serialize(r[0]) for r in rows]}


@router.get("/unread-count")
def unread_count(user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)))
    needs_action = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.requires_ack.is_(True), Notification.acknowledged_at.is_(None),
        Notification.resolved_at.is_(None)))
    return {"unread": count, "action_needed": needs_action}


@router.post("/read-all")
def read_all(user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
               .values(read_at=timeutil.utc_now()))
    db.commit()
    return {"ok": True}


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"] = "approved"
    comment: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _reason_to_reject(self):
        if self.decision == "rejected" and len((self.comment or "").strip()) < 5:
            raise ValueError("Say why you reject it (at least 5 characters)")
        return self


class AckManyIn(DecisionIn):
    ids: list[int] | None = Field(default=None, max_length=500)


@router.post("/acknowledge-many")
def acknowledge_many(body: AckManyIn, user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    """Acknowledges the chosen alerts of the signed-in user, or every open one when no ids are given."""
    now = timeutil.utc_now()
    open_ones = select(Notification.id).where(Notification.user_id == user.id, Notification.requires_ack.is_(True), Notification.acknowledged_at.is_(None))
    if body.ids is not None:
        open_ones = open_ones.where(Notification.id.in_(set(body.ids)))
    ids = list(db.scalars(open_ones))
    for nid in ids:
        record_decision(db, user, "alert", nid, body.decision == "approved", body.comment)
    if ids:
        db.execute(update(Notification).where(Notification.id.in_(ids)).values(acknowledged_at=now, read_at=func.coalesce(Notification.read_at, now)))
    db.commit()
    return {"acknowledged": len(ids)}


@router.post("/clear")
def clear(user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    """Removes this person's notifications from their list, except alerts still waiting for their decision."""
    waiting = (Notification.requires_ack.is_(True)) & Notification.acknowledged_at.is_(None) & Notification.resolved_at.is_(None)
    removed = db.execute(delete(Notification).where(Notification.user_id == user.id, ~waiting)).rowcount
    db.commit()
    return {"cleared": removed}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    n = _mine(db, user, notification_id)
    n.read_at = n.read_at or timeutil.utc_now()
    db.commit()
    return _serialize(n)


@router.post("/{notification_id}/acknowledge")
def acknowledge(notification_id: int, body: DecisionIn | None = None, user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    n = _mine(db, user, notification_id)
    now = timeutil.utc_now()
    if n.requires_ack and n.acknowledged_at is None:
        record_decision(db, user, "alert", n.id, (body.decision if body else "approved") == "approved", body.comment if body else None)
    n.acknowledged_at = n.acknowledged_at or now
    n.read_at = n.read_at or now
    db.commit()
    return _serialize(n)


@router.get("/pending-summary")
def pending_summary(location_id: int | None = None, user: User = Depends(require("report.view")),
                    db: Session = Depends(get_db)):
    """Everything outstanding, grouped by location and urgency, with the responsible person and overdue time."""
    scope = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        scope = {location_id}
    items = pending_items(db, scope, timeutil.utc_now(), hidden_templates(db, user), user)
    chosen = user.role.dashboard if user.role.tier != "manager" else None
    if chosen is not None:  # the list follows what this role's dashboard shows
        shown = set(_sections(permissions_of(user), chosen))
        items = [i for i in items if CATEGORY_SECTION.get(i["category"]) in shown]
    return {**grouped(items), "items": items[:PENDING_LIST]}
