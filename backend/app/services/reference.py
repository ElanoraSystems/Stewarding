"""Small lookup tables that many functions in one request need: loaded once per request, not once per function."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cache import memo
from ..models import Employee, Location, Shift


def shifts_by_id(db: Session) -> dict[int, Shift]:
    return memo(db, "shifts", lambda: {s.id: s for s in db.scalars(select(Shift))})


def locations_by_id(db: Session) -> dict[int, Location]:
    return memo(db, "locations", lambda: {loc.id: loc for loc in db.scalars(select(Location))})


def employee_names(db: Session) -> dict[int, str]:
    """Full name by employee id."""
    return memo(db, "employee_names", lambda: {e.id: e.full_name for e in db.scalars(select(Employee))})


def user_names(db: Session) -> dict[int, str]:
    """Full name by user id, for the people who have a login."""
    return memo(db, "user_names", lambda: {e.user_id: e.full_name for e in db.scalars(select(Employee)) if e.user_id})
