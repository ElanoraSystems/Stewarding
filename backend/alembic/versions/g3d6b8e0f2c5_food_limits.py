"""a check can have limits by type of food, and a reading names the type it was judged by

Revision ID: g3d6b8e0f2c5
Revises: f2c5a7d9e1b4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g3d6b8e0f2c5"
down_revision: Union[str, Sequence[str], None] = "f2c5a7d9e1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("equipment_schedule", sa.Column("food_limits", sa.JSON(), nullable=True))
    op.add_column("temperature_reading", sa.Column("food_type", sa.String(length=40), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.drop_column("food_type")
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.drop_column("food_limits")
