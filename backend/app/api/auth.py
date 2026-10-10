import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import current_user, permissions_of, scoped_locations
from ..models import Location, User
from ..permissions import MODULES
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILURES = 5
WINDOW_SECONDS = 900
_failures: dict[str, list[float]] = defaultdict(list)
# verifying against this keeps unknown-email and wrong-password timing alike
_DUMMY_HASH = hash_password("not-a-real-password")


class LoginIn(BaseModel):
    email: str
    password: str


def _recent_failures(email: str) -> list[float]:
    cutoff = time.monotonic() - WINDOW_SECONDS
    _failures[email] = [t for t in _failures[email] if t > cutoff]
    return _failures[email]


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if len(_recent_failures(email)) >= MAX_FAILURES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts, try again later")
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    inactive = bool(user and (not user.active or (user.employee and user.employee.status != "active")))
    if not user or not ok or inactive:
        _failures[email].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    _failures.pop(email, None)
    audit(db, user, "login", "user", user.id)
    db.commit()
    return {"access_token": create_token(user.id), "token_type": "bearer"}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    perms = permissions_of(user)
    allowed = scoped_locations(user, db)
    query = select(Location).where(Location.active.is_(True))
    if allowed is not None:
        query = query.where(Location.id.in_(allowed))
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role.name,
        "employee": {"id": user.employee.id, "name": user.employee.full_name, "code": user.employee.employee_code}
        if user.employee
        else None,
        "permissions": sorted(perms),
        "locations": [{"id": loc.id, "code": loc.code, "name": loc.name, "timezone": loc.timezone}
                      for loc in db.scalars(query.order_by(Location.name))],
        "modules": [{"key": k, "label": label} for k, label, perm in MODULES if perm in perms],
    }
