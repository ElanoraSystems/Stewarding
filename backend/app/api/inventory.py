import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
from ..deps import check_location, permissions_of, require, scoped_locations
from ..models import (Employee, InventoryBalance, InventoryCategory, InventoryItem, InventoryUnit, StockTransaction,
                      Supplier, TrackedAsset, User)
from ..pagination import paginate, row
from ..services.inventory import StockError, norm, post_txn
from ..services.similarity import SCAN_LIMIT, compact, find_similar, token_key, tokens

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

ITEM_FIELDS = ("id", "code", "name", "category_id", "unit_id", "description", "image_path",
               "storage_location", "min_level", "target_level", "opening_qty", "supplier_id", "is_tracked_asset", "active")


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class UnitIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)


MAX_LEVEL = 1_000_000
MAX_UNIT_COST = Decimal("100000")


def _clean_name(value: str | None) -> str | None:
    if value is None:
        return value
    value = " ".join(value.split())
    if len(value) < 2:
        raise ValueError("Enter an item name of at least 2 characters")
    return value


class ItemIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category_id: int
    unit_id: int
    description: str | None = Field(default=None, max_length=2000)
    storage_location: str | None = Field(default=None, max_length=80)
    min_level: int = Field(default=0, ge=0, le=MAX_LEVEL)
    target_level: int | None = Field(default=None, ge=0, le=MAX_LEVEL)
    unit_cost: Decimal | None = Field(default=None, ge=0, le=MAX_UNIT_COST)
    supplier_id: int | None = None
    is_tracked_asset: bool = False
    opening_qty: int = Field(default=0, ge=0, le=MAX_LEVEL)
    opening_location_id: int | None = None

    _name = field_validator("name")(_clean_name)

    @model_validator(mode="after")
    def _levels(self):
        if self.target_level is not None and self.target_level < self.min_level:
            raise ValueError("The target level cannot be below the minimum level")
        return self


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    category_id: int | None = None
    unit_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    storage_location: str | None = Field(default=None, max_length=80)
    min_level: int | None = Field(default=None, ge=0, le=MAX_LEVEL)
    target_level: int | None = Field(default=None, ge=0, le=MAX_LEVEL)
    unit_cost: Decimal | None = Field(default=None, ge=0, le=MAX_UNIT_COST)
    supplier_id: int | None = None
    active: bool | None = None

    _name = field_validator("name")(_clean_name)


class TxnIn(BaseModel):
    item_id: int
    location_id: int
    txn_type: Literal["receipt", "issue", "return", "damage", "adjustment"]
    qty: int = Field(ge=-MAX_LEVEL, le=MAX_LEVEL)
    reason: str | None = Field(default=None, max_length=500)


class AssetIn(BaseModel):
    item_id: int
    asset_tag: str = Field(min_length=2, max_length=40)
    location_id: int
    condition: str = Field(default="good", pattern="^(good|fair|damaged|missing)$")
    custodian_employee_id: int | None = None


class AssetUpdate(BaseModel):
    location_id: int | None = None
    condition: str | None = Field(default=None, pattern="^(good|fair|damaged|missing)$")
    custodian_employee_id: int | None = None


def _can_see_cost(user: User) -> bool:
    return bool({"inventory.manage", "stock.transfer"} & permissions_of(user))


class NameUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    active: bool | None = None


@router.get("/categories")
def list_categories(include_inactive: bool = False, user: User = Depends(require("inventory.view")),
                    db: Session = Depends(get_db)):
    stmt = select(InventoryCategory).order_by(InventoryCategory.name)
    if not include_inactive:
        stmt = stmt.where(InventoryCategory.active.is_(True))
    return [row(c, "id", "name", "active") for c in db.scalars(stmt)]


def _name_taken(db: Session, model, name: str, exclude_id: int | None = None, **scope) -> bool:
    stmt = select(model).where(*(getattr(model, k) == v for k, v in scope.items()))
    return any(norm(o.name) == norm(name) and o.id != exclude_id for o in db.scalars(stmt))


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, user: User = Depends(require("inventory.manage")), db: Session = Depends(get_db)):
    if _name_taken(db, InventoryCategory, body.name):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    category = InventoryCategory(name=" ".join(body.name.split()))
    db.add(category)
    db.flush()
    audit(db, user, "inventory.category_create", "inventory_category", category.id, None, body.model_dump())
    db.commit()
    return row(category, "id", "name", "active")


@router.put("/categories/{category_id}")
def update_category(category_id: int, body: NameUpdate, user: User = Depends(require("inventory.manage")),
                    db: Session = Depends(get_db)):
    category = db.get(InventoryCategory, category_id)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and _name_taken(db, InventoryCategory, data["name"], category.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Category already exists")
    before = {k: getattr(category, k) for k in data}
    for key, value in data.items():
        setattr(category, key, " ".join(value.split()) if key == "name" else value)
    audit(db, user, "inventory.category_update", "inventory_category", category.id, before, data)
    db.commit()
    return row(category, "id", "name", "active")


@router.get("/units")
def list_units(include_inactive: bool = False, user: User = Depends(require("inventory.view")),
               db: Session = Depends(get_db)):
    stmt = select(InventoryUnit).order_by(InventoryUnit.name)
    if not include_inactive:
        stmt = stmt.where(InventoryUnit.active.is_(True))
    return [row(u, "id", "name", "active") for u in db.scalars(stmt)]


@router.post("/units", status_code=201)
def create_unit(body: UnitIn, user: User = Depends(require("inventory.manage")), db: Session = Depends(get_db)):
    if _name_taken(db, InventoryUnit, body.name):
        raise HTTPException(status.HTTP_409_CONFLICT, "Unit already exists")
    unit = InventoryUnit(name=" ".join(body.name.split()))
    db.add(unit)
    db.flush()
    audit(db, user, "inventory.unit_create", "inventory_unit", unit.id, None, {"name": body.name})
    db.commit()
    return row(unit, "id", "name", "active")


@router.put("/units/{unit_id}")
def update_unit(unit_id: int, body: NameUpdate, user: User = Depends(require("inventory.manage")),
                db: Session = Depends(get_db)):
    unit = db.get(InventoryUnit, unit_id)
    if not unit:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and _name_taken(db, InventoryUnit, data["name"], unit.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Unit already exists")
    before = {k: getattr(unit, k) for k in data}
    for key, value in data.items():
        setattr(unit, key, " ".join(value.split()) if key == "name" else value)
    audit(db, user, "inventory.unit_update", "inventory_unit", unit.id, before, data)
    db.commit()
    return row(unit, "id", "name", "active")


def _scope(db: Session, user: User, location_id: int | None) -> set[int] | None:
    """Locations whose balances the caller may see; None means all."""
    if location_id is not None:
        check_location(user, db, location_id)
        return {location_id}
    return scoped_locations(user, db)


def _serialize_items(db: Session, user: User, items: list[InventoryItem], scope: set[int] | None) -> list[dict]:
    ids = [i.id for i in items]
    stmt = select(InventoryBalance).where(InventoryBalance.item_id.in_(ids)) if ids else None
    if stmt is not None and scope is not None:
        stmt = stmt.where(InventoryBalance.location_id.in_(scope))
    by_item: dict[int, dict[int, int]] = {}
    for bal in (db.scalars(stmt) if stmt is not None else []):
        by_item.setdefault(bal.item_id, {})[bal.location_id] = bal.qty
    received = select(StockTransaction.item_id, StockTransaction.location_id, func.sum(StockTransaction.qty_delta)).where(
        StockTransaction.qty_delta > 0, StockTransaction.item_id.in_(ids)).group_by(
        StockTransaction.item_id, StockTransaction.location_id)
    if scope is not None:
        received = received.where(StockTransaction.location_id.in_(scope))
    received_by_item: dict[int, dict[int, int]] = {}
    for item_id, location_id, total in (db.execute(received) if ids else []):
        received_by_item.setdefault(item_id, {})[location_id] = int(total)
    categories = {c.id: c.name for c in db.scalars(select(InventoryCategory))}
    units = {u.id: u.name for u in db.scalars(select(InventoryUnit))}
    suppliers = {s.id: s.name for s in db.scalars(select(Supplier))}
    show_cost = _can_see_cost(user)
    out = []
    for item in items:
        per_location = by_item.get(item.id, {})
        qty = sum(per_location.values())
        entry = {**row(item, *ITEM_FIELDS), "category": categories.get(item.category_id), "unit": units.get(item.unit_id),
                 "supplier": suppliers.get(item.supplier_id) if show_cost else None,
                 "qty": qty, "received": sum(received_by_item.get(item.id, {}).values()),
                 "received_by_location": received_by_item.get(item.id, {}), "by_location": per_location,
                 "low": qty < item.min_level}
        if show_cost:
            entry["unit_cost"] = float(item.unit_cost) if item.unit_cost is not None else None
            entry["value"] = float(qty * item.unit_cost) if item.unit_cost is not None else None
        out.append(entry)
    return out


@router.get("/items")
def list_items(search: str | None = None, category_id: int | None = None, location_id: int | None = None,
               low_only: bool = False, active: bool | None = True, page: int = 1, size: int = 25,
               user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    scope = _scope(db, user, location_id)
    stock = select(InventoryBalance.item_id, func.sum(InventoryBalance.qty).label("qty")).group_by(InventoryBalance.item_id)
    if scope is not None:
        stock = stock.where(InventoryBalance.location_id.in_(scope))
    stock = stock.subquery()
    stmt = select(InventoryItem).outerjoin(stock, stock.c.item_id == InventoryItem.id)
    if category_id is not None:
        stmt = stmt.where(InventoryItem.category_id == category_id)
    if active is not None:
        stmt = stmt.where(InventoryItem.active.is_(active))
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(InventoryItem.name.ilike(like), InventoryItem.code.ilike(like)))
    if low_only:
        stmt = stmt.where(func.coalesce(stock.c.qty, 0) < InventoryItem.min_level)
    total, rows = paginate(db, stmt.order_by(InventoryItem.code), page, size)
    items = [r[0] for r in rows]
    result = {"total": total, "items": _serialize_items(db, user, items, scope)}
    if _can_see_cost(user):
        value = db.scalar(select(func.coalesce(func.sum(stock.c.qty * InventoryItem.unit_cost), 0)).select_from(
            InventoryItem).outerjoin(stock, stock.c.item_id == InventoryItem.id))
        result["total_value"] = float(value)
    return result


def _check_links(db: Session, category_id: int | None, unit_id: int | None, supplier_id: int | None) -> None:
    """Category, unit and supplier must exist and be active."""
    if category_id is not None:
        category = db.get(InventoryCategory, category_id)
        if not category or not category.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or inactive category")
    if unit_id is not None:
        unit = db.get(InventoryUnit, unit_id)
        if not unit or not unit.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or inactive unit")
    if supplier_id is not None:
        supplier = db.get(Supplier, supplier_id)
        if not supplier or not supplier.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or inactive supplier")


def _check_duplicate(db: Session, name: str, exclude_id: int | None = None) -> None:
    """One item master entry per normalised name."""
    if name is not None:
        # the same item written differently shares a compact key (spacing, punctuation) or a token key (word order, plurals)
        clash = db.execute(select(InventoryItem.code, InventoryItem.name, InventoryItem.active).where(
            InventoryItem.id != (exclude_id or 0),
            or_(InventoryItem.name_key == norm(name), InventoryItem.compact_key == compact(name),
                InventoryItem.token_key == token_key(name))).order_by(InventoryItem.id).limit(1)).first()
        if clash:
            state = "" if clash.active else " (inactive - reactivate it instead)"
            raise HTTPException(status.HTTP_409_CONFLICT, f"{clash.name} ({clash.code}) already exists{state}")


@router.get("/items/lookup")
def similar_items(q: str, user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    """Existing items that are the same as, or close to, the typed name, so a duplicate is noticed before it is created."""
    if len(norm(q)) < 3:
        return []
    columns = (InventoryItem.id, InventoryItem.code, InventoryItem.name, InventoryItem.active)
    stmt = select(*columns)
    if db.scalar(select(func.count()).select_from(InventoryItem)) > SCAN_LIMIT:
        # a large list: only names that contain the typed letters, share a word, or start the same way are compared
        key = compact(q)
        shared = [InventoryItem.token_key.contains(w) for w in tokens(q) if len(w) >= 3]
        stmt = stmt.where(or_(InventoryItem.compact_key.contains(key), InventoryItem.compact_key.startswith(key[:3]), *shared)).limit(500)
    return find_similar(q, db.execute(stmt).all())


@router.post("/items", status_code=201)
def create_item(body: ItemIn, user: User = Depends(require("inventory.manage")), db: Session = Depends(get_db)):
    _check_links(db, body.category_id, body.unit_id, body.supplier_id)
    if body.opening_qty and body.opening_location_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Opening stock needs a location")
    name = " ".join(body.name.split())
    _check_duplicate(db, name)
    data = body.model_dump(exclude={"opening_location_id", "name"})
    item = InventoryItem(code=f"NEW-{uuid.uuid4().hex[:24]}", name=name, name_key=norm(name), **data)
    db.add(item)
    db.flush()
    number = item.id
    while db.scalar(select(InventoryItem.id).where(InventoryItem.code == f"ITM-{number:05d}")):
        number += 1
    item.code = f"ITM-{number:05d}"  # every item gets its own generated ID
    if body.opening_qty:
        check_location(user, db, body.opening_location_id)
        post_txn(db, user, item, body.opening_location_id, "opening", body.opening_qty, "Opening stock")
    audit(db, user, "inventory.item_create", "inventory_item", item.id, None, body.model_dump(mode="json"))
    db.commit()
    return _serialize_items(db, user, [item], None)[0]


@router.put("/items/{item_id}")
def update_item(item_id: int, body: ItemUpdate, user: User = Depends(require("inventory.manage")),
                db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    data = body.model_dump(exclude_unset=True)
    _check_links(db, data.get("category_id"), data.get("unit_id"), data.get("supplier_id"))
    if "name" in data:
        data["name"] = " ".join(data["name"].split())
        _check_duplicate(db, data["name"], item.id)
    minimum = data.get("min_level", item.min_level)
    target = data.get("target_level", item.target_level)
    if target is not None and target < minimum:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The target level cannot be below the minimum level")
    before = {k: str(getattr(item, k)) for k in data}
    for key, value in data.items():
        setattr(item, key, value)
    if "name" in data:
        item.name_key = norm(data["name"])
    audit(db, user, "inventory.item_update", "inventory_item", item.id, before,
          {k: str(v) for k, v in data.items()})
    db.commit()
    return _serialize_items(db, user, [item], None)[0]


def get_item_or_404(db: Session, item_id: int) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


@router.post("/transactions", status_code=201)
def post_transaction(body: TxnIn, user: User = Depends(require("stock.transfer")), db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    item = get_item_or_404(db, body.item_id)
    if not item.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{item.name} is retired; restore it before moving stock")
    if body.txn_type == "adjustment":
        if "stock.approve" not in permissions_of(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a manager can post stock adjustments")
        if body.qty == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Adjustment must not be zero")
    elif body.qty <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quantity must be positive")
    if body.txn_type in ("adjustment", "damage") and not (body.reason and len(body.reason.strip()) >= 5):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A reason is required")
    try:
        txn = post_txn(db, user, item, body.location_id, body.txn_type, body.qty, body.reason)
    except StockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    if body.txn_type == "adjustment":
        audit(db, user, "inventory.adjustment", "stock_transaction", txn.id, None,
              {"item_id": item.id, "delta": txn.qty_delta, "reason": body.reason})
    db.commit()
    return row(txn, "id", "item_id", "location_id", "txn_type", "qty_delta", "occurred_at", "user_id", "reason")


@router.get("/transactions")
def list_transactions(item_id: int | None = None, location_id: int | None = None, txn_type: str | None = None,
                      date_from: date | None = None, date_to: date | None = None, page: int = 1, size: int = 25,
                      user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    stmt = select(StockTransaction)
    scope = _scope(db, user, location_id)
    if scope is not None:
        stmt = stmt.where(StockTransaction.location_id.in_(scope))
    if item_id is not None:
        stmt = stmt.where(StockTransaction.item_id == item_id)
    if txn_type:
        stmt = stmt.where(StockTransaction.txn_type == txn_type)
    if date_from:
        stmt = stmt.where(StockTransaction.occurred_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(StockTransaction.occurred_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    total, rows = paginate(db, stmt.order_by(StockTransaction.id.desc()), page, size)
    names = dict(db.execute(select(Employee.user_id, Employee.full_name)).all())
    return {"total": total, "items": [
        {**row(t, "id", "item_id", "location_id", "txn_type", "qty_delta", "occurred_at", "reason", "ref_type", "ref_id"),
         "user": names.get(t.user_id)} for t, in rows]}


@router.get("/assets")
def list_assets(item_id: int | None = None, location_id: int | None = None,
                user: User = Depends(require("inventory.view")), db: Session = Depends(get_db)):
    stmt = select(TrackedAsset)
    scope = _scope(db, user, location_id)
    if scope is not None:
        stmt = stmt.where(TrackedAsset.location_id.in_(scope))
    if item_id is not None:
        stmt = stmt.where(TrackedAsset.item_id == item_id)
    return [row(a, "id", "item_id", "asset_tag", "location_id", "condition", "custodian_employee_id")
            for a in db.scalars(stmt.order_by(TrackedAsset.asset_tag))]


@router.post("/assets", status_code=201)
def create_asset(body: AssetIn, user: User = Depends(require("inventory.manage")), db: Session = Depends(get_db)):
    item = get_item_or_404(db, body.item_id)
    if not item.is_tracked_asset:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Item is not configured as a tracked asset")
    check_location(user, db, body.location_id)
    asset = TrackedAsset(**body.model_dump())
    try:
        db.add(asset)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Asset tag already exists") from None
    audit(db, user, "inventory.asset_create", "tracked_asset", asset.id, None, body.model_dump())
    db.commit()
    return row(asset, "id", "item_id", "asset_tag", "location_id", "condition", "custodian_employee_id")


@router.put("/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetUpdate, user: User = Depends(require("inventory.count")),
                 db: Session = Depends(get_db)):
    asset = db.get(TrackedAsset, asset_id)
    if not asset:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    check_location(user, db, asset.location_id)
    data = body.model_dump(exclude_unset=True)
    if "location_id" in data:
        check_location(user, db, data["location_id"])
    before = {k: getattr(asset, k) for k in data}
    for key, value in data.items():
        setattr(asset, key, value)
    audit(db, user, "inventory.asset_update", "tracked_asset", asset.id, before, data)
    db.commit()
    return row(asset, "id", "item_id", "asset_tag", "location_id", "condition", "custodian_employee_id")
