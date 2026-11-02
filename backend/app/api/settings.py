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
from ..models import Location, Role, Setting, User
from ..pagination import row
from ..services.notify import CATEGORIES, ROUTES_KEY, routes
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


DEFAULT_WHO = {"attendance": "Managers and supervisors at the location (by role type)", "checklists": "Stewards and supervisors at the location, limited to the checklist's job titles; escalations to supervisors and managers",
               "monitoring": "Stewards and supervisors at the location for what is due; supervisors and managers for the rest", "stock": "Supervisors and managers",
               "breakage": "Supervisors and managers", "summary": "Supervisors and managers"}


class RoutesIn(BaseModel):
    routes: dict[str, list[str] | None]


def _routes_payload(db: Session) -> dict:
    chosen = routes(db)
    return {"categories": [{"key": k, "label": label, "about": about, "default": DEFAULT_WHO[k]} for k, (label, about) in CATEGORIES.items()],
            "roles": [{"name": r.name, "label": r.label or r.name, "tier": r.tier} for r in db.scalars(select(Role).order_by(Role.id))],
            "routes": {k: chosen.get(k) for k in CATEGORIES}}


@router.get("/notification-routes")
def read_routes(user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    """Which roles receive each kind of alert; a kind with no roles chosen keeps the default, which goes by role type."""
    return _routes_payload(db)


@router.put("/notification-routes")
def update_routes(body: RoutesIn, user: User = Depends(require("settings.manage")), db: Session = Depends(get_db)):
    unknown = set(body.routes) - set(CATEGORIES)
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown kind of alert: {sorted(unknown)[0]}")
    known = set(db.scalars(select(Role.name)))
    for names in body.routes.values():
        if names is not None and set(names) - known:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown role")
    before = routes(db)
    after = {k: list(dict.fromkeys(v)) for k, v in body.routes.items() if v is not None}  # null puts a kind back to the default
    record = db.get(Setting, ROUTES_KEY)
    if record:
        record.value = {"v": after}
    else:
        db.add(Setting(key=ROUTES_KEY, value={"v": after}))
    db.flush()
    audit(db, user, "notification_routes.update", "setting", None, before, after)
    db.commit()
    return _routes_payload(db)


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
