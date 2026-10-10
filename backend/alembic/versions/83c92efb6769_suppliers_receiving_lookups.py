"""suppliers, receiving documents and managed lists

Revision ID: 83c92efb6769
Revises: 0b6064ed67ab
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "83c92efb6769"
down_revision: Union[str, Sequence[str], None] = "0b6064ed67ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def upgrade() -> None:
    op.create_table(
        "supplier",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("name_key", sa.String(120), nullable=False, unique=True),
        sa.Column("contact", sa.String(120)),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(200)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "lookup_value",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("value", sa.String(120), nullable=False),
        sa.Column("value_key", sa.String(120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("kind", "value_key"),
    )
    op.create_index("ix_lookup_value_kind", "lookup_value", ["kind"])

    with op.batch_alter_table("inventory_category") as batch:
        batch.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("inventory_unit") as batch:
        batch.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("inventory_item") as batch:
        batch.add_column(sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("supplier.id", name="fk_item_supplier")))
        batch.add_column(sa.Column("name_key", sa.String(120), nullable=False, server_default=""))

    bind = op.get_bind()
    items = sa.table("inventory_item", sa.column("id", sa.Integer), sa.column("name", sa.String),
                     sa.column("supplier", sa.String), sa.column("supplier_id", sa.Integer), sa.column("name_key", sa.String))
    suppliers = sa.table("supplier", sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("name_key", sa.String))
    seen: dict[str, int] = {}
    for item_id, name, supplier in bind.execute(sa.select(items.c.id, items.c.name, items.c.supplier)).all():
        values = {"name_key": _key(name)}
        if supplier and supplier.strip():
            key = _key(supplier)
            if key not in seen:
                bind.execute(suppliers.insert().values(name=supplier.strip(), name_key=key))
                seen[key] = bind.execute(sa.select(suppliers.c.id).where(suppliers.c.name_key == key)).scalar_one()
            values["supplier_id"] = seen[key]
        bind.execute(items.update().where(items.c.id == item_id).values(**values))

    with op.batch_alter_table("inventory_item") as batch:
        batch.drop_column("supplier")
        batch.create_index("ix_inventory_item_supplier_id", ["supplier_id"])
        batch.create_index("ix_inventory_item_name_key", ["name_key"])
        batch.create_unique_constraint("uq_inventory_item_kind_name_key", ["kind", "name_key"])

    op.create_table(
        "receipt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("supplier.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id"), nullable=False),
        sa.Column("invoice_number", sa.String(60), nullable=False),
        sa.Column("invoice_date", sa.DateTime()),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("received_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("total", sa.Numeric(12, 2)),
        sa.Column("voided_by", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("voided_at", sa.DateTime()),
        sa.Column("void_reason", sa.Text()),
    )
    op.create_index("uq_receipt_supplier_invoice", "receipt", ["supplier_id", "invoice_number"], unique=True,
                    sqlite_where=sa.text("status = 'posted'"), postgresql_where=sa.text("status = 'posted'"))
    op.create_index("ix_receipt_supplier_id", "receipt", ["supplier_id"])
    op.create_index("ix_receipt_location_id", "receipt", ["location_id"])
    op.create_index("ix_receipt_received_at", "receipt", ["received_at"])
    op.create_table(
        "receipt_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipt.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_item.id"), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(10, 2)),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("stock_transaction.id"), unique=True),
    )
    op.create_index("ix_receipt_line_receipt_id", "receipt_line", ["receipt_id"])
    op.create_index("ix_receipt_line_item_id", "receipt_line", ["item_id"])


def downgrade() -> None:
    op.drop_table("receipt_line")
    op.drop_table("receipt")
    with op.batch_alter_table("inventory_item") as batch:
        batch.drop_constraint("uq_inventory_item_kind_name_key", type_="unique")
        batch.drop_index("ix_inventory_item_name_key")
        batch.drop_index("ix_inventory_item_supplier_id")
        batch.add_column(sa.Column("supplier", sa.String(120)))
    op.execute("UPDATE inventory_item SET supplier = (SELECT name FROM supplier WHERE supplier.id = inventory_item.supplier_id)")
    with op.batch_alter_table("inventory_item") as batch:
        batch.drop_column("supplier_id")
        batch.drop_column("name_key")
    with op.batch_alter_table("inventory_unit") as batch:
        batch.drop_column("active")
    with op.batch_alter_table("inventory_category") as batch:
        batch.drop_column("active")
    op.drop_index("ix_lookup_value_kind", table_name="lookup_value")
    op.drop_table("lookup_value")
    op.drop_table("supplier")
