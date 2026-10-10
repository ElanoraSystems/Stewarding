from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import ts


class InventoryCategory(Base):
    __tablename__ = "inventory_category"
    __table_args__ = (UniqueConstraint("kind", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # crockery | smallware
    name: Mapped[str] = mapped_column(String(80))


class InventoryUnit(Base):
    __tablename__ = "inventory_unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)


class InventoryItem(Base):
    __tablename__ = "inventory_item"
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
    supplier: Mapped[str | None] = mapped_column(String(120))
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
