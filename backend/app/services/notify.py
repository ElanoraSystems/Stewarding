from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..models import Employee, EmployeeLocation, Equipment, Location, Notification, Role, RolePermission, ScanEvent, ShiftAssignment, User
from ..permissions import MANAGER
from .push import queue
from .settings import get_setting


def _working_here(db: Session, location_id: int) -> set[int]:
    """Users who are at the location without being assigned to it: rostered there today, or who scanned its QR code within the scan window."""
    now = timeutil.utc_now()
    place = db.get(Location, location_id)
    day = timeutil.local_date(now, place.timezone) if place else now.date()
    rostered = [a for a in db.scalars(select(ShiftAssignment).where(ShiftAssignment.location_id == location_id, ShiftAssignment.weekday == day.weekday()))
                if a.applies_on(day)]
    users = set(db.scalars(select(Employee.user_id).where(Employee.id.in_({a.employee_id for a in rostered}), Employee.user_id.is_not(None)))) if rostered else set()
    since = now - timedelta(minutes=get_setting(db, "scan.valid_minutes"))
    points = select(Equipment.id).where(Equipment.location_id == location_id)
    users |= set(db.scalars(select(ScanEvent.user_id).where(ScanEvent.created_at >= since, or_(
        and_(ScanEvent.kind == "location", ScanEvent.target_id == location_id),
        and_(ScanEvent.kind == "equipment", ScanEvent.target_id.in_(points))))))
    return users


def recipients(db: Session, location_id: int | None, *roles: str) -> list[int]:
    """Active users whose role behaves like one of `roles` (a tier) at the location; managers are included when asked for.

    "At the location" means assigned to it, rostered there today, or having scanned its QR code within the scan window,
    so staff who move between outlets get the reminders of the outlet they are working at."""
    base = (
        select(User.id)
        .join(Role, User.role_id == Role.id)
        .join(Employee, Employee.user_id == User.id)
        .where(User.active.is_(True), Employee.status == "active", Role.tier.in_(roles))
    )
    non_manager = [r for r in roles if r != MANAGER]
    ids: set[int] = set()
    if MANAGER in roles:
        ids |= set(db.scalars(base.where(Role.tier == MANAGER)))
    if non_manager and location_id is not None:
        q = base.join(EmployeeLocation, EmployeeLocation.employee_id == Employee.id).where(
            EmployeeLocation.location_id == location_id, Role.tier.in_(non_manager)
        )
        ids |= set(db.scalars(q))
        here = _working_here(db, location_id)
        if here:
            ids |= set(db.scalars(base.where(User.id.in_(here), Role.tier.in_(non_manager))))
    return sorted(ids)


def holders_of(db: Session, permission: str, location_id: int | None = None) -> list[int]:
    """Active users whose role grants `permission`: managers everywhere, other roles at the location."""
    base = (
        select(User.id)
        .join(Role, User.role_id == Role.id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Employee, Employee.user_id == User.id)
        .where(User.active.is_(True), Employee.status == "active", RolePermission.permission == permission)
    )
    ids = set(db.scalars(base.where(Role.tier == MANAGER)))
    if location_id is not None:
        ids |= set(db.scalars(base.join(EmployeeLocation, EmployeeLocation.employee_id == Employee.id).where(
            EmployeeLocation.location_id == location_id, Role.tier != MANAGER)))
    return sorted(ids)


def notify(db: Session, user_ids, kind: str, title: str, *, key: str, body: str | None = None,
           priority: str = "normal", location_id: int | None = None, link: str | None = None,
           due_at=None, requires_ack: bool = False) -> int:
    """One notification per recipient and `key`; returns how many were newly created."""
    created = 0
    for uid in set(user_ids):
        if db.scalar(select(Notification.id).where(Notification.user_id == uid, Notification.dedupe_key == key)):
            continue
        db.add(Notification(user_id=uid, kind=kind, title=title, body=body, priority=priority,
                            location_id=location_id, link=link, dedupe_key=key, due_at=due_at,
                            requires_ack=requires_ack))
        db.flush()
        queue(db, uid, title, body, link, priority, key)
        created += 1
    return created
