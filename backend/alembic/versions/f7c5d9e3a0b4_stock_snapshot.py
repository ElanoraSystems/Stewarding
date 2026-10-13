"""month-end stock snapshots

Revision ID: f7c5d9e3a0b4
Revises: e6b4c8d2f9a3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7c5d9e3a0b4"
down_revision: Union[str, Sequence[str], None] = "e6b4c8d2f9a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stock_snapshot",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("location.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("inventory_item.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("built_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("location_id", "month", "item_id", name="uq_stock_snapshot"),
    )
    op.create_index("ix_stock_snapshot_location_id", "stock_snapshot", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_snapshot_location_id", table_name="stock_snapshot")
    op.drop_table("stock_snapshot")
