"""a time-in check can say how long it may stay open before its time out is due

Revision ID: a1c5e9b3d7f2
Revises: z0b4d8f2a6c1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c5e9b3d7f2"
down_revision: Union[str, Sequence[str], None] = "z0b4d8f2a6c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("equipment_schedule", sa.Column("max_open_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("equipment_schedule", "max_open_minutes")
