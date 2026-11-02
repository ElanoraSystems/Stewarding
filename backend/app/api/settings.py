from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..services.deletion import delete_if_unused
from ..db import get_db
from ..deps import require
from ..models import Location, Setting, User
from ..pagination import row
from ..services.settings import DEFAULTS, LIMITS, all_settings
from ..services.snapshots import forget_from

router = APIRouter(prefix="/api/settings", tags=["settings"])

LOCATION_FIELDS = ("id", "code", "name", "kind", "timezone", "active")


class SettingsIn(BaseModel):
    values: dict[str, int] = Field(min_length=1)


class LocationIn(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(pattern="^(kitchen|restaurant|bar|banquet|station|other)$")
    timezone: str


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: str | None = Field(default=None, pattern="^(kitchen|restaurant|bar|banquet|station|other)$")
    timezone: str | None = None
    active: bool | None = None


def _check_tz(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown time zone") from None


def _location(loc: Location) -> dict:
    return row(loc, *LOCATION_FIELDS)


@router.get("")
def read_settings(user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    return {"settings": all_settings(db), "limits": LIMITS, "locations": [_location(loc) for loc in db.scalars(select(Location).order_by(Location.name))]}


@router.put("")
def update_settings(body: SettingsIn, user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    unknown = set(body.values) - set(DEFAULTS)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {sorted(unknown)[0]}")
    for key, value in body.values.items():
        low, high = LIMITS[key]
        if not low <= value <= high:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{key} must be between {low} and {high}")
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
    loc = Location(**body.model_dump())
    try:
        db.add(loc)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Location code already exists") from None
    audit(db, user, "location.create", "location", loc.id, None, body.model_dump())
    db.commit()
    return _location(loc)


@router.put("/locations/{location_id}")
def update_location(location_id: int, body: LocationUpdate, user: User = Depends(require("settings.manage")),
                    db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    data = body.model_dump(exclude_unset=True)
    if "timezone" in data:
        _check_tz(data["timezone"])
    before = {k: getattr(loc, k) for k in data}
    if "timezone" in data and data["timezone"] != loc.timezone:
        forget_from(db, loc.id)  # month boundaries move with the time zone, so stored month-end balances no longer apply
    for key, value in data.items():
        setattr(loc, key, value)
    audit(db, user, "location.update", "location", loc.id, before, data)
    db.commit()
    return _location(loc)


@router.delete("/locations/{location_id}")
def delete_location(location_id: int, user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Location not found")
    before = {"code": loc.code, "name": loc.name}
    delete_if_unused(db, loc, loc.name)
    audit(db, user, "location.delete", "location", location_id, before, None)
    db.commit()
    return {"deleted": location_id}
