from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from .. import timeutil
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import Notification, User
from ..pagination import paginate, row
from ..services.summary import grouped, pending_items

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

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


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    n = _mine(db, user, notification_id)
    n.read_at = n.read_at or timeutil.utc_now()
    db.commit()
    return _serialize(n)


@router.post("/{notification_id}/acknowledge")
def acknowledge(notification_id: int, user: User = Depends(require("notification.view")), db: Session = Depends(get_db)):
    n = _mine(db, user, notification_id)
    now = timeutil.utc_now()
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
    items = pending_items(db, scope, timeutil.utc_now())
    return {**grouped(items), "items": items}
