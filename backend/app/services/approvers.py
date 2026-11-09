"""Who may approve a given checklist or monitoring log: people named on it, any one of whom can decide.
Nobody named means everyone who holds the approval permission at that location, as before. A manager can always step in."""
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Employee, Role, RolePermission, User
from ..permissions import MANAGER

CHECKLISTS = "checklist.verify"
MONITORING = "temp.review"


def may_decide(user: User, approvers: list[int] | None) -> bool:
    """True when nobody is named, the person is one of those named, or they are a manager."""
    return user.role.tier == MANAGER or not approvers or user.id in approvers


def candidates(db: Session, permission: str) -> list[dict]:
    """Active people with a login whose role lets them approve this kind of work, so only people who can actually decide are offered."""
    allowed = set(db.scalars(select(RolePermission.role_id).where(RolePermission.permission == permission)))
    allowed |= set(db.scalars(select(Role.id).where(Role.tier == MANAGER)))
    rows = db.execute(select(User, Employee).join(Employee, Employee.user_id == User.id)
                      .where(User.active.is_(True), Employee.status == "active", User.role_id.in_(allowed or {0})).order_by(Employee.full_name))
    return [{"id": u.id, "name": e.full_name, "job_title": e.job_title} for u, e in rows]


def clean(db: Session, ids: list[int] | None, permission: str) -> list[int] | None:
    """The chosen people, without repeats, each checked to be someone who can approve; nothing chosen means everyone as before."""
    chosen = list(dict.fromkeys(ids or []))
    if not chosen:
        return None
    ok = {c["id"]: c["name"] for c in candidates(db, permission)}
    for uid in chosen:
        if uid not in ok:
            who = db.scalar(select(Employee.full_name).where(Employee.user_id == uid))
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{who or 'That person'} cannot approve this: their role does not allow it, or they are not active")
    return chosen


def names_of(db: Session, ids: list[int] | None) -> list[str]:
    if not ids:
        return []
    by = {e.user_id: e.full_name for e in db.scalars(select(Employee).where(Employee.user_id.in_(ids)))}
    return [by.get(i, "Former employee") for i in ids]


def active_ids(db: Session, ids: list[int] | None) -> list[int]:
    return list(db.scalars(select(User.id).where(User.id.in_(ids or [0]), User.active.is_(True))))
