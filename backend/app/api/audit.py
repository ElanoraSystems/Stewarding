from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require
from ..models import AuditLog, Employee, User
from ..pagination import paginate, row

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(user_id: int | None = None, action: str | None = None, entity: str | None = None,
               date_from: date | None = None, date_to: date | None = None, page: int = 1, size: int = 25,
               user: User = Depends(require("audit.view")), db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    total, rows = paginate(db, stmt.order_by(AuditLog.id.desc()), page, size)
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    return {"total": total, "items": [
        {**row(a, "id", "created_at", "user_id", "action", "entity", "entity_id", "before", "after"),
         "user": names.get(a.user_id)} for a, in rows]}
