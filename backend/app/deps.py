from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import EmployeeLocation, Location, User
from .permissions import MANAGER
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if user.employee and user.employee.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Employee account is inactive")
    return user


def permissions_of(user: User) -> set[str]:
    return {p.permission for p in user.role.permissions}


def require(permission: str):
    """Dependency factory: 403 unless the user's role grants `permission`."""

    def dep(user: User = Depends(current_user)) -> User:
        if permission not in permissions_of(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
        return user

    return dep


def scoped_locations(user: User, db: Session) -> set[int] | None:
    """Location ids the user may touch; None means every location (manager)."""
    if user.role.name == MANAGER:
        return None
    if not user.employee:
        return set()
    rows = db.scalars(select(EmployeeLocation.location_id).where(EmployeeLocation.employee_id == user.employee.id))
    return set(rows)


def check_location(user: User, db: Session, location_id: int) -> None:
    """404 for an unknown location, 403 when it is outside the user's scope."""
    if not db.get(Location, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    allowed = scoped_locations(user, db)
    if allowed is not None and location_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Location not assigned to you")
