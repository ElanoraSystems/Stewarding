"""a time-in entry can carry its own time before the time out is due

Revision ID: c6e0b2d8f4a5
Revises: b5d9a1c7e3f4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6e0b2d8f4a5"
down_revision: Union[str, Sequence[str], None] = "b5d9a1c7e3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.add_column(sa.Column("expected_minutes", sa.Integer))


def downgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.drop_column("expected_minutes")
