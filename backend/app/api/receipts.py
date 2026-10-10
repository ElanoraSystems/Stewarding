from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import Employee, InventoryItem, Receipt, ReceiptLine, Supplier, User
from ..pagination import paginate, row
from ..services.inventory import StockError, post_txn

router = APIRouter(prefix="/api/receipts", tags=["receiving"])

DocType = Literal["receipt", "supplier_return"]
LABEL = {"receipt": "Goods receipt", "supplier_return": "Return to supplier"}
FIELDS = ("id", "doc_type", "supplier_id", "location_id", "invoice_number", "received_at", "received_by", "note",
          "status", "voided_by", "voided_at", "void_reason")


class LineIn(BaseModel):
    item_id: int
    qty: int = Field(gt=0, le=100000)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class ReceiptIn(BaseModel):
    doc_type: DocType = "receipt"
    supplier_id: int
    location_id: int
    invoice_number: str = Field(min_length=1, max_length=60)
    invoice_date: date | None = None
    note: str | None = Field(default=None, max_length=1000)
    update_costs: bool = False
    lines: list[LineIn] = Field(min_length=1, max_length=200)


class VoidIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


def _serialize(db: Session, receipt: Receipt, lines: bool = False) -> dict:
    out = row(receipt, *FIELDS)
    out["invoice_date"] = receipt.invoice_date.date().isoformat() if receipt.invoice_date else None
    out["total"] = float(receipt.total) if receipt.total is not None else None
    out["supplier"] = db.scalar(select(Supplier.name).where(Supplier.id == receipt.supplier_id))
    out["received_by_name"] = db.scalar(select(Employee.full_name).where(Employee.user_id == receipt.received_by))
    if lines:
        items = {i.id: i for i in db.scalars(select(InventoryItem))}
        out["lines"] = [{"item_id": ln.item_id, "code": items[ln.item_id].code, "name": items[ln.item_id].name,
                         "qty": ln.qty, "unit_cost": float(ln.unit_cost) if ln.unit_cost is not None else None,
                         "transaction_id": ln.transaction_id}
                        for ln in db.scalars(select(ReceiptLine).where(ReceiptLine.receipt_id == receipt.id).order_by(ReceiptLine.id))]
    return out


def _get(db: Session, user: User, receipt_id: int) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if not receipt:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found")
    check_location(user, db, receipt.location_id)
    return receipt


@router.post("", status_code=201)
def post_receipt(body: ReceiptIn, user: User = Depends(require("stock.transfer")), db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    supplier = db.get(Supplier, body.supplier_id)
    if not supplier or not supplier.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown or inactive supplier")
    ids = [ln.item_id for ln in body.lines]
    if len(set(ids)) != len(ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Each item can appear once; combine the quantities")
    items = {i.id: i for i in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(ids)))}
    for item_id in ids:
        if item_id not in items or not items[item_id].active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown or inactive item (id {item_id})")
    invoice = " ".join(body.invoice_number.split()).upper()
    duplicate = db.scalar(select(Receipt).where(Receipt.supplier_id == supplier.id, Receipt.invoice_number == invoice,
                                                Receipt.status == "posted"))
    if duplicate:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Invoice {invoice} from {supplier.name} was already posted (document #{duplicate.id})")

    costs = [ln.qty * ln.unit_cost for ln in body.lines if ln.unit_cost is not None]
    receipt = Receipt(doc_type=body.doc_type, supplier_id=supplier.id, location_id=body.location_id, invoice_number=invoice,
                      invoice_date=datetime.combine(body.invoice_date, datetime.min.time()) if body.invoice_date else None,
                      received_at=timeutil.utc_now(), received_by=user.id, note=body.note, total=sum(costs) if costs else None)
    try:
        db.add(receipt)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Invoice {invoice} from {supplier.name} was already posted") from None

    txn_type = "receipt" if body.doc_type == "receipt" else "issue"
    reason = f"{LABEL[body.doc_type]} #{receipt.id}, invoice {invoice} ({supplier.name})"
    cost_changes = {}
    try:
        for ln in body.lines:
            item = items[ln.item_id]
            txn = post_txn(db, user, item, body.location_id, txn_type, ln.qty, reason, "receipt", receipt.id)
            db.add(ReceiptLine(receipt_id=receipt.id, item_id=item.id, qty=ln.qty, unit_cost=ln.unit_cost, transaction_id=txn.id))
            if body.update_costs and body.doc_type == "receipt" and ln.unit_cost is not None and item.unit_cost != ln.unit_cost:
                cost_changes[item.code] = {"from": f"{item.unit_cost:.2f}" if item.unit_cost is not None else None,
                                           "to": f"{ln.unit_cost:.2f}"}
                item.unit_cost = ln.unit_cost
    except StockError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    audit(db, user, "receipt.post", "receipt", receipt.id, None,
          {"doc_type": body.doc_type, "supplier": supplier.name, "invoice": invoice, "lines": len(body.lines),
           "cost_updates": cost_changes})
    db.commit()
    return _serialize(db, receipt, lines=True)


@router.get("")
def list_receipts(supplier_id: int | None = None, location_id: int | None = None, receipt_status: str | None = None,
                  q: str | None = None, date_from: date | None = None, date_to: date | None = None, page: int = 1,
                  size: int = 25, user: User = Depends(require("stock.transfer")), db: Session = Depends(get_db)):
    stmt = select(Receipt)
    scope = scoped_locations(user, db)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(Receipt.location_id == location_id)
    elif scope is not None:
        stmt = stmt.where(Receipt.location_id.in_(scope))
    if supplier_id is not None:
        stmt = stmt.where(Receipt.supplier_id == supplier_id)
    if receipt_status:
        stmt = stmt.where(Receipt.status == receipt_status)
    if q:
        stmt = stmt.where(or_(Receipt.invoice_number.ilike(f"%{q.strip()}%"), Receipt.note.ilike(f"%{q.strip()}%")))
    if date_from:
        stmt = stmt.where(Receipt.received_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Receipt.received_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    total, rows = paginate(db, stmt.order_by(Receipt.id.desc()), page, size)
    return {"total": total, "items": [_serialize(db, r[0]) for r in rows]}


@router.get("/{receipt_id}")
def get_receipt(receipt_id: int, user: User = Depends(require("stock.transfer")), db: Session = Depends(get_db)):
    return _serialize(db, _get(db, user, receipt_id), lines=True)


@router.post("/{receipt_id}/void")
def void_receipt(receipt_id: int, body: VoidIn, user: User = Depends(require("stock.approve")),
                 db: Session = Depends(get_db)):
    """Reverses a posted document with new ledger entries; nothing already posted is edited."""
    receipt = _get(db, user, receipt_id)
    if receipt.status != "posted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Document is already void")
    sign = -1 if receipt.doc_type == "receipt" else 1
    reason = f"Void of {LABEL[receipt.doc_type].lower()} #{receipt.id}: {body.reason}"
    for ln in db.scalars(select(ReceiptLine).where(ReceiptLine.receipt_id == receipt.id)):
        post_txn(db, user, db.get(InventoryItem, ln.item_id), receipt.location_id, "adjustment", sign * ln.qty, reason,
                 "receipt_void", receipt.id, allow_negative=True)
    receipt.status, receipt.voided_by, receipt.voided_at, receipt.void_reason = "void", user.id, timeutil.utc_now(), body.reason
    audit(db, user, "receipt.void", "receipt", receipt.id, {"status": "posted"}, {"status": "void", "reason": body.reason})
    db.commit()
    return _serialize(db, receipt, lines=True)
