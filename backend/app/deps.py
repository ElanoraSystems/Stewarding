from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cache import memo
from .db import get_db
from .models import EmployeeLocation, Location, User
from .permissions import MANAGER
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


PASSWORD_PATHS = ("/api/auth/me", "/api/auth/change-password")


def current_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    decoded = decode_token(creds.credentials) if creds else None
    user = db.get(User, decoded[0]) if decoded else None
    if not user or not user.active or user.token_version != decoded[1]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if user.must_change_password and request.url.path not in PASSWORD_PATHS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Change your password before continuing")
    if user.employee and user.employee.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Employee account is inactive")
    return user


def permissions_of(user: User) -> set[str]:
    return {p.permission for p in user.role.permissions}


def role_names(user: User) -> set[str]:
    """The names tasks may be assigned to for this user: their own role and the tier it behaves like."""
    return {user.role.name, user.role.tier}


def require(permission: str):
    """Dependency factory: 403 unless the user's role grants `permission`."""

    def dep(user: User = Depends(current_user)) -> User:
        if permission not in permissions_of(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
        return user

    return dep


def scoped_locations(user: User, db: Session) -> set[int] | None:
    """Location ids the user may touch; None means every location (manager)."""
    if user.role.tier == MANAGER:
        return None
    if not user.employee:
        return set()
    employee_id = user.employee.id
    return memo(db, ("scope", employee_id), lambda: set(db.scalars(
        select(EmployeeLocation.location_id).where(EmployeeLocation.employee_id == employee_id))))


def check_location(user: User, db: Session, location_id: int) -> None:
    """404 for an unknown location, 403 when it is outside the user's scope."""
    if not db.get(Location, location_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    allowed = scoped_locations(user, db)
    if allowed is not None and location_id not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Location not assigned to you")
