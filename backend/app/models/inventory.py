from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import ts


class InventoryCategory(Base):
    __tablename__ = "inventory_category"
    __table_args__ = (UniqueConstraint("kind", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # crockery | smallware
    name: Mapped[str] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryUnit(Base):
    __tablename__ = "inventory_unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Supplier(Base):
    __tablename__ = "supplier"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    name_key: Mapped[str] = mapped_column(String(120), unique=True)  # lower-cased name, blocks case-only duplicates
    contact: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryItem(Base):
    __tablename__ = "inventory_item"
    # one item master entry per normalised name within a kind
    __table_args__ = (UniqueConstraint("kind", "name_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("inventory_category.id"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("inventory_unit.id"))
    description: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(300))
    storage_location: Mapped[str | None] = mapped_column(String(80))
    min_level: Mapped[int] = mapped_column(Integer, default=0)
    target_level: Mapped[int | None] = mapped_column(Integer)
    opening_qty: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), index=True)
    name_key: Mapped[str] = mapped_column(String(120), default="", index=True)  # normalised name per kind for duplicate checks
    is_tracked_asset: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class InventoryBalance(Base):
    """Derived from stock_transaction and only changed in the same transaction as one."""

    __tablename__ = "inventory_balance"
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)


class StockTransaction(Base):
    __tablename__ = "stock_transaction"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), index=True)
    # opening | receipt | issue | transfer_in | transfer_out | return | damage | breakage | adjustment
    txn_type: Mapped[str] = mapped_column(String(20), index=True)
    qty_delta: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = ts(index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(30))
    ref_id: Mapped[int | None] = mapped_column(Integer)


@event.listens_for(StockTransaction, "before_update")
@event.listens_for(StockTransaction, "before_delete")
def _immutable(*_):
    raise ValueError("Stock transactions are immutable; post an adjustment instead")


class InventoryCount(Base):
    __tablename__ = "inventory_count"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    counted_at: Mapped[datetime] = ts()
    counted_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | posted
    month: Mapped[str | None] = mapped_column(String(7))  # YYYY-MM for reconciliation


class InventoryCountLine(Base):
    __tablename__ = "inventory_count_line"
    __table_args__ = (UniqueConstraint("count_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    count_id: Mapped[int] = mapped_column(ForeignKey("inventory_count.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id"))
    system_qty: Mapped[int] = mapped_column(Integer)
    counted_qty: Mapped[int] = mapped_column(Integer)
    adjustment_txn_id: Mapped[int | None] = mapped_column(ForeignKey("stock_transaction.id"))


class InventoryTransfer(Base):
    __tablename__ = "inventory_transfer"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), index=True)
    to_location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    requested_at: Mapped[datetime] = ts()
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)
    note: Mapped[str | None] = mapped_column(Text)


class InventoryTransferLine(Base):
    __tablename__ = "inventory_transfer_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("inventory_transfer.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id"))
    qty: Mapped[int] = mapped_column(Integer)


class TrackedAsset(Base):
    __tablename__ = "tracked_asset"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id"), index=True)
    asset_tag: Mapped[str] = mapped_column(String(40), unique=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"))
    condition: Mapped[str] = mapped_column(String(20), default="good")
    custodian_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employee.id"))


class Receipt(Base):
    """A goods receipt or return-to-supplier document; posting it writes ledger rows referencing it."""

    __tablename__ = "receipt"
    # the same supplier invoice cannot be posted twice; a voided receipt frees its number for correct re-entry
    __table_args__ = (Index("uq_receipt_supplier_invoice", "supplier_id", "invoice_number", unique=True,
                            sqlite_where=text("status = 'posted'"), postgresql_where=text("status = 'posted'")),)
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(20), default="receipt")  # receipt | supplier_return
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(60))
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime)
    received_at: Mapped[datetime] = ts(index=True)
    received_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="posted")  # posted | void
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    voided_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime)
    void_reason: Mapped[str | None] = mapped_column(Text)


class ReceiptLine(Base):
    __tablename__ = "receipt_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipt.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_item.id"), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("stock_transaction.id"), unique=True)
