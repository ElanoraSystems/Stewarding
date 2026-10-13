from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import require
from ..models import Location, Setting, User
from ..pagination import row
from ..security import hash_password
from ..services.settings import DEFAULTS, all_settings
from ..services.snapshots import forget_from

router = APIRouter(prefix="/api/settings", tags=["settings"])

MAX_SETTING = 100_000
LOCATION_FIELDS = ("id", "code", "name", "kind", "timezone", "active")


class SettingsIn(BaseModel):
    values: dict[str, int] = Field(min_length=1)


class LocationIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern="^(kitchen|restaurant|bar|banquet|station|other)$")
    timezone: str
    pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: str | None = Field(default=None, pattern="^(kitchen|restaurant|bar|banquet|station|other)$")
    timezone: str | None = None
    active: bool | None = None
    pin: str | None = Field(default=None, pattern=r"^\d{4,8}$")
    clear_pin: bool = False


def _check_tz(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown time zone") from None


def _location(loc: Location) -> dict:
    return {**row(loc, *LOCATION_FIELDS), "pin_required": loc.checkin_pin_hash is not None}


@router.get("")
def read_settings(user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    return {"settings": all_settings(db), "locations": [_location(loc) for loc in db.scalars(select(Location).order_by(Location.name))]}


@router.put("")
def update_settings(body: SettingsIn, user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    unknown = set(body.values) - set(DEFAULTS)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {sorted(unknown)[0]}")
    if any(v < 0 or v > MAX_SETTING for v in body.values.values()):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Values must be between 0 and {MAX_SETTING}")
    if body.values.get("approval.checklists", 0) not in (0, 1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "approval.checklists must be 0 or 1")
    before = all_settings(db)
    for key, value in body.values.items():
        record = db.get(Setting, key)
        if record:
            record.value = {"v": value}
        else:
            db.add(Setting(key=key, value={"v": value}))
    db.flush()
    audit(db, user, "settings.update", "setting", None, {k: before[k] for k in body.values}, body.values)
    db.commit()
    return {"settings": all_settings(db)}


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    _check_tz(body.timezone)
    loc = Location(code=body.code, name=body.name, kind=body.kind, timezone=body.timezone,
                   checkin_pin_hash=hash_password(body.pin) if body.pin else None)
    try:
        db.add(loc)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Location code already exists") from None
    audit(db, user, "location.create", "location", loc.id, None, {**body.model_dump(exclude={"pin"}), "pin_set": bool(body.pin)})
    db.commit()
    return _location(loc)


@router.put("/locations/{location_id}")
def update_location(location_id: int, body: LocationUpdate, user: User = Depends(require("settings.manage")),
                    db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    data = body.model_dump(exclude_unset=True, exclude={"pin", "clear_pin"})
    if "timezone" in data:
        _check_tz(data["timezone"])
    before = {k: getattr(loc, k) for k in data}
    if "timezone" in data and data["timezone"] != loc.timezone:
        forget_from(db, loc.id)  # month boundaries move with the time zone, so stored month-end balances no longer apply
    for key, value in data.items():
        setattr(loc, key, value)
    pin_changed = False
    if body.clear_pin:
        loc.checkin_pin_hash, pin_changed = None, True
    elif body.pin:
        loc.checkin_pin_hash, pin_changed = hash_password(body.pin), True
    audit(db, user, "location.update", "location", loc.id, before, {**data, "pin_changed": pin_changed})
    db.commit()
    return _location(loc)
