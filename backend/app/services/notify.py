from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..cache import memo
from ..models import Setting, Employee, EmployeeLocation, Equipment, Location, Notification, Role, RolePermission, ScanEvent, ShiftAssignment, User
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


CATEGORIES = {
    "attendance": ("Attendance", "No check-in, missed check-out"),
    "checklists": ("Checklists", "Tasks due, overdue and escalated; tasks waiting for approval"),
    "monitoring": ("Monitoring", "Checks due and overdue, failed checks, time outs, retests"),
    "stock": ("Stock", "Low stock, counts, transfers"),
    "breakage": ("Breakage", "Breakage to review"),
    "summary": ("Daily summary", "The morning list of what is pending"),
}
ROUTES_KEY = "notify.routes"


def routes(db: Session) -> dict[str, list[str]]:
    """The roles chosen to receive each kind of alert (role names); a kind that is missing keeps the default, which goes by role type."""
    def build() -> dict[str, list[str]]:
        row = db.get(Setting, ROUTES_KEY)
        return dict(row.value["v"]) if row else {}
    return memo(db, "notify_routes", build)


def recipients(db: Session, location_id: int | None, *roles: str, category: str | None = None) -> list[int]:
    """Active users whose role behaves like one of `roles` (a tier) at the location; managers are included when asked for.
    When a person has chosen the roles for this `category`, those roles are used instead of the tiers.

    "At the location" means assigned to it, rostered there today, or having scanned its QR code within the scan window,
    so staff who move between outlets get the reminders of the outlet they are working at."""
    base = (
        select(User.id)
        .join(Role, User.role_id == Role.id)
        .join(Employee, Employee.user_id == User.id)
        .where(User.active.is_(True), Employee.status == "active")
    )
    chosen = routes(db).get(category) if category else None
    if chosen is not None:
        who = db.execute(select(User.id, Role.tier).join(Role, User.role_id == Role.id).join(Employee, Employee.user_id == User.id)
                         .where(User.active.is_(True), Employee.status == "active", Role.name.in_(chosen or [""]))).all()
        here: set[int] = set()
        if location_id is not None:
            here = _working_here(db, location_id) | set(db.scalars(select(Employee.user_id).join(EmployeeLocation, EmployeeLocation.employee_id == Employee.id)
                                                                   .where(EmployeeLocation.location_id == location_id, Employee.user_id.is_not(None))))
        return sorted(user_id for user_id, tier in who if tier == MANAGER or user_id in here)  # a manager hears about every place; others where they are
    non_manager = [r for r in roles if r != MANAGER]
    base = base.where(Role.tier.in_(roles))
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
