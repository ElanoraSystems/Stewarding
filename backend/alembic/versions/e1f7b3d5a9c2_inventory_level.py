"""a minimum stock level per item and location

Revision ID: e1f7b3d5a9c2
Revises: d0e6a2c4f8b1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f7b3d5a9c2"
down_revision: Union[str, Sequence[str], None] = "d0e6a2c4f8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inventory_level",
        sa.Column("item_id", sa.Integer, sa.ForeignKey("inventory_item.id"), primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("location.id"), primary_key=True),
        sa.Column("min_level", sa.Integer, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("inventory_level")
