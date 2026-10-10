"""single inventory, receipt discounts, week off and absences

Revision ID: 92be1edbdd16
Revises: 83c92efb6769
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "92be1edbdd16"
down_revision: Union[str, Sequence[str], None] = "83c92efb6769"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Names SQLite gives the unnamed (kind, name) unique constraint when it is reflected for a batch rebuild.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_N_name)s"}


def _key(text: str) -> str:
    return " ".join(text.lower().split())


def _merge_duplicates(bind) -> None:
    """Crockery and smallware used to be separate namespaces; one list needs unique category and item names."""
    cats = sa.table("inventory_category", sa.column("id", sa.Integer), sa.column("name", sa.String))
    items = sa.table("inventory_item", sa.column("id", sa.Integer), sa.column("code", sa.String), sa.column("name", sa.String),
                     sa.column("name_key", sa.String), sa.column("category_id", sa.Integer))
    keep: dict[str, int] = {}
    for cat_id, name in bind.execute(sa.select(cats.c.id, cats.c.name).order_by(cats.c.id)).all():
        key = _key(name)
        if key in keep:
            bind.execute(items.update().where(items.c.category_id == cat_id).values(category_id=keep[key]))
            bind.execute(cats.delete().where(cats.c.id == cat_id))
        else:
            keep[key] = cat_id
    seen: set[str] = set()
    for item_id, code, name, key in bind.execute(
            sa.select(items.c.id, items.c.code, items.c.name, items.c.name_key).order_by(items.c.id)).all():
        if key in seen:
            name = f"{name} ({code})"
            key = _key(name)
            if key in seen:
                name, key = f"{name} #{item_id}", _key(f"{name} #{item_id}")
            bind.execute(items.update().where(items.c.id == item_id).values(name=name, name_key=key))
        seen.add(key)


def upgrade() -> None:
    bind = op.get_bind()
    _merge_duplicates(bind)
    postgres = bind.dialect.name == "postgresql"

    old_category_unique = "inventory_category_kind_name_key" if postgres else "uq_inventory_category_kind_name"
    with op.batch_alter_table("inventory_category", naming_convention=NAMING) as batch:
        batch.drop_constraint(old_category_unique, type_="unique")
        batch.drop_column("kind")
        batch.create_unique_constraint("uq_inventory_category_name", ["name"])

    with op.batch_alter_table("inventory_item") as batch:
        batch.drop_constraint("uq_inventory_item_kind_name_key", type_="unique")
        batch.drop_index("ix_inventory_item_kind")
        batch.drop_column("kind")
        batch.create_unique_constraint("uq_inventory_item_name_key", ["name_key"])

    with op.batch_alter_table("inventory_count") as batch:
        batch.drop_column("kind")

    with op.batch_alter_table("receipt") as batch:
        batch.add_column(sa.Column("subtotal", sa.Numeric(12, 2)))
        batch.add_column(sa.Column("line_discount_total", sa.Numeric(12, 2)))
        batch.add_column(sa.Column("discount_type", sa.String(10)))
        batch.add_column(sa.Column("discount_value", sa.Numeric(12, 2)))
        batch.add_column(sa.Column("discount_amount", sa.Numeric(12, 2)))
    with op.batch_alter_table("receipt_line") as batch:
        batch.add_column(sa.Column("discount_type", sa.String(10)))
        batch.add_column(sa.Column("discount_value", sa.Numeric(12, 2)))
        batch.add_column(sa.Column("discount_amount", sa.Numeric(12, 2)))
        batch.add_column(sa.Column("line_total", sa.Numeric(12, 2)))
    # existing documents had no discounts, so their gross figures equal what was stored
    op.execute("UPDATE receipt SET subtotal = total, line_discount_total = 0, discount_amount = 0 WHERE total IS NOT NULL")
    op.execute("UPDATE receipt_line SET line_total = qty * unit_cost, discount_amount = 0 WHERE unit_cost IS NOT NULL")

    with op.batch_alter_table("shift") as batch:
        batch.add_column(sa.Column("kind", sa.String(10), nullable=False, server_default="work"))

    op.create_table(
        "absence_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id"), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id"), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("absence_type", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("recorded_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("voided_by", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("voided_at", sa.DateTime()),
        sa.Column("void_reason", sa.Text()),
    )
    op.create_index("uq_absence_employee_day", "absence_record", ["employee_id", "local_date"], unique=True,
                    sqlite_where=sa.text("voided_at IS NULL"), postgresql_where=sa.text("voided_at IS NULL"))
    op.create_index("ix_absence_record_employee_id", "absence_record", ["employee_id"])
    op.create_index("ix_absence_record_location_id", "absence_record", ["location_id"])
    op.create_index("ix_absence_record_local_date", "absence_record", ["local_date"])


def downgrade() -> None:
    """Structural only: every item and category returns as crockery because the old type is not kept."""
    op.drop_table("absence_record")
    with op.batch_alter_table("shift") as batch:
        batch.drop_column("kind")
    with op.batch_alter_table("receipt_line") as batch:
        for column in ("line_total", "discount_amount", "discount_value", "discount_type"):
            batch.drop_column(column)
    with op.batch_alter_table("receipt") as batch:
        for column in ("discount_amount", "discount_value", "discount_type", "line_discount_total", "subtotal"):
            batch.drop_column(column)
    with op.batch_alter_table("inventory_count") as batch:
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="crockery"))
    with op.batch_alter_table("inventory_item") as batch:
        batch.drop_constraint("uq_inventory_item_name_key", type_="unique")
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="crockery"))
        batch.create_index("ix_inventory_item_kind", ["kind"])
        batch.create_unique_constraint("uq_inventory_item_kind_name_key", ["kind", "name_key"])
    with op.batch_alter_table("inventory_category") as batch:
        batch.drop_constraint("uq_inventory_category_name", type_="unique")
        batch.add_column(sa.Column("kind", sa.String(20), nullable=False, server_default="crockery"))
        postgres = op.get_bind().dialect.name == "postgresql"
        batch.create_unique_constraint("inventory_category_kind_name_key" if postgres else "uq_inventory_category_kind_name", ["kind", "name"])
