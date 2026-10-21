from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, current_user, permissions_of, require, scoped_locations
from ..models import (Employee, Equipment, FoodItem, Location, Lot, LotEvent, LotLink, ReadingLot, ShelfLifeRule, Supplier, TemperatureReading,
                      User)
from ..pagination import iso, paginate
from ..services import exporters, labels
from ..services.monitoring import describe
from ..services.organization import report_identity, stamp
from ..services.traceability import (CONDITIONS, GROUPS, STATUSES, LotError, ancestors, child_code, descendants, new_code, usable,
                                     use_by_for)

router = APIRouter(prefix="/api/lots", tags=["food traceability"])

Received = Literal["chilled_raw", "vacuum_chilled", "frozen"]
Group = Literal["poultry", "red_meat", "seafood", "dairy", "eggs", "other"]


def any_of(*needed: str):
    """Dependency: 403 unless the user's role grants at least one of the permissions."""

    def dep(user: User = Depends(current_user)) -> User:
        if not set(needed) & permissions_of(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
        return user

    return dep


def _clean(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    return value or None


class ReceiveIn(BaseModel):
    food_item_id: int
    location_id: int
    condition: Received
    supplier_id: int | None = None
    supplier_lot: str | None = Field(default=None, max_length=60)
    produced_on: date | None = None
    expiry_on: date | None = None
    temp_c: Decimal | None = Field(default=None, ge=-60, le=80)
    qty: Decimal | None = Field(default=None, ge=0, le=1000000)
    unit: str | None = Field(default=None, max_length=20)
    pack_count: int | None = Field(default=None, ge=1, le=10000)
    tag_number: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _dates(self):
        if self.produced_on and self.expiry_on and self.expiry_on < self.produced_on:
            raise ValueError("The expiry date cannot be before the production date")
        return self


class PartIn(BaseModel):
    description: str = Field(min_length=2, max_length=120)
    count: int = Field(ge=1, le=1000)
    condition: Literal["chilled_raw", "vacuum_chilled", "frozen", "thawed"]
    qty: Decimal | None = Field(default=None, ge=0, le=1000000)
    unit: str | None = Field(default=None, max_length=20)
    use_by: datetime | None = None

    @field_validator("description")
    @classmethod
    def _tidy(cls, value: str) -> str:
        return " ".join(value.split())


class SplitIn(BaseModel):
    parts: list[PartIn] = Field(min_length=1, max_length=30)
    finish_parent: bool = False


class StatusIn(BaseModel):
    status: Literal["active", "used_up", "discarded", "on_hold"]
    note: str | None = Field(default=None, max_length=300)


class RuleIn(BaseModel):
    food_group: Group
    condition: Literal["chilled_raw", "vacuum_chilled", "frozen", "thawed", "cooked_chilled"]
    hours: int = Field(ge=1, le=8760)
    note: str | None = Field(default=None, max_length=300)


class FoodItemIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    food_group: Group


class FoodItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    food_group: Group | None = None
    active: bool | None = None


def _maps(db: Session) -> dict:
    return {"item": dict(db.execute(select(FoodItem.id, FoodItem.name)).all()), "supplier": dict(db.execute(select(Supplier.id, Supplier.name)).all()),
            "location": dict(db.execute(select(Location.id, Location.name)).all()), "tz": dict(db.execute(select(Location.id, Location.timezone)).all()),
            "user": dict(db.execute(select(Employee.user_id, Employee.full_name)).all())}


def _local(moment: datetime | None, tz: str) -> str:
    return timeutil.to_local(moment, tz).strftime("%d %b %Y %H:%M") if moment else ""


def _day(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else ""


def _lot(lot: Lot, maps: dict, now: datetime) -> dict:
    return {"id": lot.id, "code": lot.code, "kind": lot.kind, "food_item_id": lot.food_item_id, "item": maps["item"].get(lot.food_item_id),
            "food_group": lot.food_group, "group_label": GROUPS[lot.food_group][0], "condition": lot.condition,
            "condition_label": CONDITIONS[lot.condition], "supplier_id": lot.supplier_id, "supplier": maps["supplier"].get(lot.supplier_id),
            "supplier_lot": lot.supplier_lot, "produced_on": lot.produced_on.isoformat() if lot.produced_on else None,
            "expiry_on": lot.expiry_on.isoformat() if lot.expiry_on else None, "use_by": iso(lot.use_by),
            "past_use_by": bool(lot.use_by and lot.use_by < now), "temp_c": float(lot.temp_c) if lot.temp_c is not None else None,
            "qty": float(lot.qty) if lot.qty is not None else None, "unit": lot.unit, "pack_count": lot.pack_count,
            "pack_description": lot.pack_description, "tag_number": lot.tag_number, "location_id": lot.location_id,
            "location": maps["location"].get(lot.location_id), "status": lot.status, "note": lot.note,
            "created_by_name": maps["user"].get(lot.created_by), "created_at": iso(lot.created_at), "thawed_at": iso(lot.thawed_at)}


def _scoped(stmt, user: User, db: Session):
    allowed = scoped_locations(user, db)
    return stmt if allowed is None else stmt.where(Lot.location_id.in_(allowed))


def _get(db: Session, user: User, lot_id: int) -> Lot:
    lot = db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lot not found")
    check_location(user, db, lot.location_id)
    return lot


def _initials(name: str | None) -> str:
    return "".join(part[0] for part in (name or "").split()[:2]).upper()


def _label(lot: Lot, maps: dict) -> dict:
    tz = maps["tz"][lot.location_id]
    portion = lot.kind == "portion"
    amount = " ".join(part for part in (f"{lot.qty:g}" if lot.qty is not None else "", lot.unit or "") if part)
    if portion:
        detail = f"{lot.pack_count} x {lot.pack_description}" if lot.pack_count and lot.pack_description else (lot.pack_description or "")
    else:
        detail = ", ".join(part for part in (amount, f"tag {lot.tag_number}" if lot.tag_number else "") if part)
    return {"code": lot.code, "item": maps["item"].get(lot.food_item_id) or "", "detail": detail, "condition": CONDITIONS[lot.condition],
            "supplier": maps["supplier"].get(lot.supplier_id) or "", "supplier_lot": lot.supplier_lot or "", "produced": _day(lot.produced_on),
            "expiry": _day(lot.expiry_on), "stamp_label": "Thawed" if lot.thawed_at else "Portioned" if portion else "Received",
            "stamped": _local(lot.thawed_at or lot.created_at, tz), "by": _initials(maps["user"].get(lot.thawed_by or lot.created_by)), "use_by": _local(lot.use_by, tz), "location": maps["location"].get(lot.location_id) or ""}


@router.get("/rules")
def list_rules(user: User = Depends(any_of("lot.view", "lot.receive", "lot.split", "lot.manage")), db: Session = Depends(get_db)):
    rules = db.scalars(select(ShelfLifeRule).order_by(ShelfLifeRule.food_group, ShelfLifeRule.condition))
    return {"groups": [{"key": k, "label": v[0]} for k, v in GROUPS.items()], "conditions": [{"key": k, "label": v} for k, v in CONDITIONS.items()],
            "rules": [{"id": r.id, "food_group": r.food_group, "condition": r.condition, "hours": r.hours, "note": r.note} for r in rules]}


@router.put("/rules")
def save_rule(body: RuleIn, user: User = Depends(require("lot.manage")), db: Session = Depends(get_db)):
    rule = db.scalar(select(ShelfLifeRule).where(ShelfLifeRule.food_group == body.food_group, ShelfLifeRule.condition == body.condition))
    before = rule.hours if rule else None
    if rule:
        rule.hours, rule.note = body.hours, _clean(body.note)
    else:
        rule = ShelfLifeRule(food_group=body.food_group, condition=body.condition, hours=body.hours, note=_clean(body.note))
        db.add(rule)
    db.flush()
    audit(db, user, "lot.rule_save", "shelf_life_rule", rule.id, {"hours": before}, {"group": body.food_group, "condition": body.condition, "hours": body.hours})
    db.commit()
    return {"id": rule.id, "food_group": rule.food_group, "condition": rule.condition, "hours": rule.hours, "note": rule.note}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, user: User = Depends(require("lot.manage")), db: Session = Depends(get_db)):
    rule = db.get(ShelfLifeRule, rule_id)
    if not rule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    audit(db, user, "lot.rule_delete", "shelf_life_rule", rule.id, {"group": rule.food_group, "condition": rule.condition, "hours": rule.hours}, None)
    db.delete(rule)
    db.commit()
    return {"deleted": rule_id}


@router.get("/suppliers")
def list_suppliers(user: User = Depends(any_of("lot.receive", "lot.manage")), db: Session = Depends(get_db)):
    """Active suppliers, so receiving does not depend on a stock permission."""
    return [{"id": s.id, "name": s.name} for s in db.scalars(select(Supplier).where(Supplier.active.is_(True)).order_by(Supplier.name))]


def _item_dict(item: FoodItem) -> dict:
    return {"id": item.id, "name": item.name, "food_group": item.food_group, "group_label": GROUPS[item.food_group][0], "active": item.active}


@router.get("/food-items")
def list_food_items(include_inactive: bool = False, user: User = Depends(any_of("lot.view", "lot.receive", "lot.split", "lot.manage")),
                    db: Session = Depends(get_db)):
    stmt = select(FoodItem).order_by(FoodItem.name)
    if not include_inactive:
        stmt = stmt.where(FoodItem.active.is_(True))
    return [_item_dict(i) for i in db.scalars(stmt)]


def _name_free(db: Session, name: str, exclude: int | None = None) -> bool:
    return db.scalar(select(FoodItem.id).where(FoodItem.name.ilike(name), FoodItem.id != (exclude or 0))) is None


@router.post("/food-items", status_code=201)
def create_food_item(body: FoodItemIn, user: User = Depends(require("lot.manage")), db: Session = Depends(get_db)):
    name = " ".join(body.name.split())
    if not _name_free(db, name):
        raise HTTPException(status.HTTP_409_CONFLICT, "A food item with that name already exists")
    item = FoodItem(name=name, food_group=body.food_group)
    db.add(item)
    db.flush()
    audit(db, user, "lot.food_item_create", "food_item", item.id, None, {"name": name, "food_group": body.food_group})
    db.commit()
    return _item_dict(item)


@router.put("/food-items/{item_id}")
def update_food_item(item_id: int, body: FoodItemUpdate, user: User = Depends(require("lot.manage")), db: Session = Depends(get_db)):
    item = db.get(FoodItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Food item not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data:
        data["name"] = " ".join(data["name"].split())
        if not _name_free(db, data["name"], item.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "A food item with that name already exists")
    for key, value in data.items():
        setattr(item, key, value)
    audit(db, user, "lot.food_item_update", "food_item", item.id, None, data)
    db.commit()
    return _item_dict(item)


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=60), limit: int = Query(15, ge=1, le=50),
           user: User = Depends(any_of("lot.view", "lot.split", "temp.record")), db: Session = Depends(get_db)):
    """Active lots matching a typed code or item name, for pickers; those past their use-by are flagged."""
    like = f"%{q.strip()}%"
    stmt = _scoped(select(Lot).join(FoodItem, FoodItem.id == Lot.food_item_id).where(
        Lot.status == "active", or_(Lot.code.ilike(like), FoodItem.name.ilike(like), Lot.supplier_lot.ilike(like))), user, db)
    maps, now = _maps(db), timeutil.utc_now()
    return [{"id": lot.id, "code": lot.code, "item": maps["item"].get(lot.food_item_id), "use_by": iso(lot.use_by), "past_use_by": bool(lot.use_by and lot.use_by < now),
             "condition_label": CONDITIONS[lot.condition], "location": maps["location"].get(lot.location_id), "pack": lot.pack_description}
            for lot in db.scalars(stmt.order_by(Lot.id.desc()).limit(limit))]


@router.get("/by-code/{code}")
def by_code(code: str, user: User = Depends(any_of("lot.view", "lot.split", "temp.record")), db: Session = Depends(get_db)):
    """What a scanned or typed code refers to, and whether it may be used right now."""
    lot = db.scalar(select(Lot).where(Lot.code == code.strip().upper()))
    if not lot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No lot has that code")
    check_location(user, db, lot.location_id)
    now = timeutil.utc_now()
    return {**_lot(lot, _maps(db), now), "blocked": usable(lot, now)}


def label_pages(db: Session, user: User, lot_ids: list[int], copies: int) -> list[dict]:
    """The label content for each lot, repeated per copy, for lots the user may see."""
    maps = _maps(db)
    return [_label(_get(db, user, lot_id), maps) for lot_id in lot_ids for _ in range(copies)]


@router.get("/labels")
def print_labels(ids: str = Query(max_length=600), copies: int = Query(1, ge=1, le=50), fmt: Literal["pdf", "zpl"] = "pdf",
                 dpi: int = Query(203, ge=150, le=600), user: User = Depends(any_of("lot.view", "lot.receive", "lot.split")), db: Session = Depends(get_db)):
    """75 x 50 mm labels, one per copy, as a PDF to print or as ZPL for a Zebra printer."""
    try:
        wanted = [int(part) for part in ids.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ids must be lot numbers separated by commas") from None
    if not wanted or len(wanted) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose between 1 and 100 lots")
    pages = label_pages(db, user, wanted, copies)
    if fmt == "zpl":
        return Response(labels.labels_zpl(pages, dpi), media_type="text/plain", headers={"Content-Disposition": 'attachment; filename="lot-labels.zpl"'})
    return Response(labels.labels_pdf(pages), media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="lot-labels.pdf"'})


@router.get("")
def list_lots(q: str | None = None, lot_status: str | None = Query(None, alias="status"), food_group: str | None = None,
              location_id: int | None = None, expiring_hours: int | None = Query(None, ge=1, le=8760), page: int = 1, size: int = 25,
              user: User = Depends(require("lot.view")), db: Session = Depends(get_db)):
    stmt = _scoped(select(Lot).join(FoodItem, FoodItem.id == Lot.food_item_id), user, db)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Lot.code.ilike(like), FoodItem.name.ilike(like), Lot.supplier_lot.ilike(like)))
    if lot_status in STATUSES:
        stmt = stmt.where(Lot.status == lot_status)
    if food_group in GROUPS:
        stmt = stmt.where(Lot.food_group == food_group)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(Lot.location_id == location_id)
    now = timeutil.utc_now()
    if expiring_hours:
        stmt = stmt.where(Lot.status == "active", Lot.use_by.is_not(None), Lot.use_by <= now + timedelta(hours=expiring_hours))
    total, rows = paginate(db, stmt.order_by(Lot.id.desc()), page, size)
    maps = _maps(db)
    return {"total": total, "items": [_lot(r[0], maps, now) for r in rows]}


@router.post("", status_code=201)
def receive_lot(body: ReceiveIn, user: User = Depends(require("lot.receive")), db: Session = Depends(get_db)):
    """A delivery line becomes a lot with its own code, the supplier's details and a use-by date."""
    check_location(user, db, body.location_id)
    item = db.get(FoodItem, body.food_item_id)
    if not item or not item.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a food item from the list")
    if body.supplier_id is not None and not db.get(Supplier, body.supplier_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown supplier")
    tz = db.get(Location, body.location_id).timezone
    now = timeutil.utc_now()
    use_by = use_by_for(db, item.food_group, body.condition, now, body.expiry_on, tz, rule_required=False)
    lot = Lot(code=new_code(db, item.food_group, timeutil.local_date(now, tz)), kind="received", food_item_id=item.id, food_group=item.food_group,
              condition=body.condition, supplier_id=body.supplier_id, supplier_lot=_clean(body.supplier_lot), produced_on=body.produced_on,
              expiry_on=body.expiry_on, use_by=use_by, temp_c=body.temp_c, qty=body.qty, unit=_clean(body.unit), pack_count=body.pack_count,
              tag_number=_clean(body.tag_number), location_id=body.location_id, note=_clean(body.note), created_by=user.id, created_at=now)
    db.add(lot)
    db.flush()
    audit(db, user, "lot.receive", "lot", lot.id, None, {"code": lot.code, "item": item.name, "supplier_lot": lot.supplier_lot})
    db.commit()
    return _lot(lot, _maps(db), now)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


@router.post("/{lot_id}/split", status_code=201)
def split_lot(lot_id: int, body: SplitIn, user: User = Depends(require("lot.split")), db: Session = Depends(get_db)):
    """Opening a lot into portion lots: each keeps the parent's supplier and dates, gets its own code and a use-by from the shelf-life rule."""
    parent = _get(db, user, lot_id)
    now = timeutil.utc_now()
    reason = usable(parent, now)
    if reason:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{reason}, so it cannot be split")
    tz = db.get(Location, parent.location_id).timezone
    manager = "lot.manage" in permissions_of(user)
    made = []
    for part in body.parts:
        if parent.condition == "thawed" and part.condition != "thawed":
            raise HTTPException(status.HTTP_409_CONFLICT, "Thawed food keeps only on its thawed shelf life and cannot be frozen or re-stored; portion it as thawed")
        if part.condition == "thawed" and parent.condition != "thawed":
            raise HTTPException(status.HTTP_409_CONFLICT, "Thaw the lot first, then portion it")
        try:
            use_by = use_by_for(db, parent.food_group, part.condition, now, parent.expiry_on, tz, rule_required=True)
        except LotError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        if parent.use_by and (use_by is None or parent.use_by < use_by):
            use_by = parent.use_by
        if part.use_by:
            chosen = _naive_utc(part.use_by)
            if chosen < now:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "The use-by date is already past")
            if use_by is not None and chosen > use_by and not manager:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a manager can set a use-by later than the shelf-life rule allows")
            use_by = chosen
        child = Lot(code=child_code(db, parent), kind="portion", food_item_id=parent.food_item_id, food_group=parent.food_group, condition=part.condition,
                    supplier_id=parent.supplier_id, supplier_lot=parent.supplier_lot, produced_on=parent.produced_on, expiry_on=parent.expiry_on,
                    use_by=use_by, qty=part.qty, unit=_clean(part.unit), pack_count=part.count, pack_description=part.description,
                    tag_number=parent.tag_number, location_id=parent.location_id, created_by=user.id, created_at=now)
        db.add(child)
        db.flush()
        db.add(LotLink(parent_id=parent.id, child_id=child.id))
        made.append(child)
    codes = ", ".join(c.code for c in made)
    db.add(LotEvent(lot_id=parent.id, kind="split", detail=f"Split into {codes}"[:300], user_id=user.id, at=now))
    if body.finish_parent:
        parent.status = "used_up"
        db.add(LotEvent(lot_id=parent.id, kind="status", detail="Used up after splitting", user_id=user.id, at=now))
    audit(db, user, "lot.split", "lot", parent.id, None, {"parent": parent.code, "children": [c.code for c in made]})
    db.commit()
    maps = _maps(db)
    return {"parent": _lot(parent, maps, now), "lots": [_lot(c, maps, now) for c in made]}


@router.post("/{lot_id}/thaw")
def thaw_lot(lot_id: int, user: User = Depends(require("lot.split")), db: Session = Depends(get_db)):
    """A frozen lot becomes thawed once: its use-by is reset by the thawed shelf-life rule, never past the supplier's expiry."""
    lot = _get(db, user, lot_id)
    now = timeutil.utc_now()
    reason = usable(lot, now)
    if reason:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{reason}, so it cannot be thawed")
    if lot.condition != "frozen":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a frozen lot can be thawed" if lot.condition != "thawed" else "This lot is already thawed and cannot be thawed again")
    tz = db.get(Location, lot.location_id).timezone
    try:
        use_by = use_by_for(db, lot.food_group, "thawed", now, lot.expiry_on, tz, rule_required=True)
    except LotError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    was = lot.use_by
    lot.condition, lot.thawed_at, lot.thawed_by, lot.use_by = "thawed", now, user.id, use_by
    db.add(LotEvent(lot_id=lot.id, kind="thaw", detail=f"Thawed; use by {_local(use_by, tz)}"[:300], user_id=user.id, at=now))
    audit(db, user, "lot.thaw", "lot", lot.id, {"use_by": iso(was)}, {"use_by": iso(use_by)})
    db.commit()
    return _lot(lot, _maps(db), now)


@router.post("/{lot_id}/status")
def set_status(lot_id: int, body: StatusIn, user: User = Depends(any_of("lot.split", "lot.manage")), db: Session = Depends(get_db)):
    """Used up or discarded by the butcher or a manager; hold, release and reopening are for managers."""
    lot = _get(db, user, lot_id)
    manager = "lot.manage" in permissions_of(user)
    ordinary = body.status in ("used_up", "discarded") and lot.status == "active"
    if not (manager or ordinary):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a manager can hold, release or reopen a lot")
    note = _clean(body.note)
    if body.status in ("discarded", "on_hold") and (note is None or len(note) < 3):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say why in a few words")
    now = timeutil.utc_now()
    if body.status == lot.status:
        return _lot(lot, _maps(db), now)
    before = lot.status
    lot.status = body.status
    db.add(LotEvent(lot_id=lot.id, kind="status", detail=f"{before.replace('_', ' ')} to {body.status.replace('_', ' ')}" + (f": {note}" if note else ""),
                    user_id=user.id, at=now))
    audit(db, user, "lot.status", "lot", lot.id, {"status": before}, {"status": body.status, "note": note})
    db.commit()
    return _lot(lot, _maps(db), now)


def _uses(db: Session, lot_ids: list[int], maps: dict, codes: dict[int, str]) -> list[dict]:
    if not lot_ids:
        return []
    rows = db.execute(select(TemperatureReading, Equipment, ReadingLot.lot_id).join(ReadingLot, ReadingLot.reading_id == TemperatureReading.id)
                      .join(Equipment, Equipment.id == TemperatureReading.equipment_id).where(ReadingLot.lot_id.in_(lot_ids))
                      .order_by(TemperatureReading.recorded_at)).all()
    return [{"reading_id": r.id, "lot_id": lot_id, "lot_code": codes[lot_id], "at": iso(r.recorded_at), "equipment": eq.name, "stage": r.stage,
             "display": describe(r), "passed": r.passed, "by": maps["user"].get(r.recorded_by), "rejected": r.rejected_at is not None,
             "tz": maps["tz"].get(r.location_id)} for r, eq, lot_id in rows]


def _trace(db: Session, lot: Lot) -> dict:
    now = timeutil.utc_now()
    maps = _maps(db)
    back, forward = ancestors(db, lot.id), descendants(db, lot.id)
    codes = {x.id: x.code for x in [lot, *back, *forward]}
    return {"lot": _lot(lot, maps, now), "back": [_lot(x, maps, now) for x in back], "forward": [_lot(x, maps, now) for x in forward],
            "uses_back": _uses(db, [x.id for x in back], maps, codes), "uses_forward": _uses(db, [lot.id, *[x.id for x in forward]], maps, codes),
            "events": [{"kind": e.kind, "detail": e.detail, "by": maps["user"].get(e.user_id), "at": iso(e.at)}
                       for e in db.scalars(select(LotEvent).where(LotEvent.lot_id == lot.id).order_by(LotEvent.id))]}


@router.get("/{lot_id}")
def lot_detail(lot_id: int, user: User = Depends(require("lot.view")), db: Session = Depends(get_db)):
    """The lot, where it came from, what was made from it, the checks that used it and its history."""
    return _trace(db, _get(db, user, lot_id))


def _moment(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text.rstrip("Z")) if text else None


@router.get("/{lot_id}/trace/export")
def export_trace(lot_id: int, user: User = Depends(require("lot.view")), db: Session = Depends(get_db)):
    """A printable trace of one lot, back to the supplier and forward to every cooking record."""
    lot = _get(db, user, lot_id)
    traced = _trace(db, lot)
    identity = report_identity(db)
    now = timeutil.utc_now()
    tz = identity["timezone"]
    employee = user.employee
    zones = {i: z for i, z in db.execute(select(Location.id, Location.timezone))}

    def lot_row(x: dict) -> dict:
        zone = zones[x["location_id"]]
        return {"code": x["code"], "item": x["item"], "type": "Portions" if x["kind"] == "portion" else "Delivery", "supplier": x["supplier"] or "",
                "supplier_lot": x["supplier_lot"] or "", "produced": _day(date.fromisoformat(x["produced_on"])) if x["produced_on"] else "",
                "expiry": _day(date.fromisoformat(x["expiry_on"])) if x["expiry_on"] else "", "created": _local(_moment(x["created_at"]), zone),
                "use_by": _local(_moment(x["use_by"]), zone), "status": x["status"].replace("_", " "), "location": x["location"] or ""}

    lot_columns = [("code", "Lot"), ("item", "Item"), ("type", "Type"), ("supplier", "Supplier"), ("supplier_lot", "Supplier lot"), ("produced", "Produced"),
                   ("expiry", "Expiry"), ("created", "Received or portioned"), ("use_by", "Use by"), ("status", "Status"), ("location", "Location")]
    use_columns = [("when", "When"), ("lot", "Lot"), ("equipment", "Monitoring point"), ("stage", "Check"), ("value", "Recorded"), ("result", "Result"), ("by", "By")]

    def use_row(u: dict) -> dict:
        return {"when": _local(_moment(u["at"]), u["tz"] or tz), "lot": u["lot_code"], "equipment": u["equipment"], "stage": u["stage"],
                "value": u["display"], "result": "PASS" if u["passed"] else "FAIL", "by": u["by"] or ""}

    groups = [{"title": f"Lot {lot.code}", "meta": [], "columns": lot_columns, "rows": [lot_row(traced["lot"])], "totals": []},
              {"title": "Came from (back to the supplier)", "meta": [], "columns": lot_columns, "rows": [lot_row(x) for x in traced["back"]], "totals": [],
               "empty": "Nothing before it: this lot came straight from the supplier"},
              {"title": "Checks recorded on the lots it came from", "meta": [], "columns": use_columns, "rows": [use_row(u) for u in traced["uses_back"]], "totals": [], "empty": "No checks were recorded on those lots"},
              {"title": "Made from this lot (forward)", "meta": [], "columns": lot_columns, "rows": [lot_row(x) for x in traced["forward"]],
               "totals": [("Portion lots", str(len(traced["forward"])))], "empty": "Nothing has been made from this lot yet"},
              {"title": "Checks recorded on this lot and what was made from it, including cooking", "meta": [], "columns": use_columns,
               "rows": [use_row(u) for u in traced["uses_forward"]], "totals": [("Records", str(len(traced["uses_forward"])))],
               "empty": "No cooking or other check has used this lot yet"}]
    doc = {"title": f"Food trace - {lot.code}", "period": {"label": f"Traced {stamp(now, tz)}"}, "locations": [traced["lot"]["location"] or ""],
           "prepared_by": employee.full_name if employee else user.email, "prepared_position": employee.job_title if employee else (user.role.label or user.role.name),
           "generated_at": stamp(now, tz), "organization": identity, "groups": groups}
    audit(db, user, "lot.trace_export", "lot", lot.id, None, {"code": lot.code})
    db.commit()
    return Response(exporters.record_to_pdf(doc), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="trace-{lot.code}.pdf"'})
