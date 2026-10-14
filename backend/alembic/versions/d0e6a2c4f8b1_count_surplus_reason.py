"""a reason on count lines that find more than the system holds

Revision ID: d0e6a2c4f8b1
Revises: c9d5f1b3e7a0
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0e6a2c4f8b1"
down_revision: Union[str, Sequence[str], None] = "c9d5f1b3e7a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("inventory_count_line") as batch:
        batch.add_column(sa.Column("reason", sa.Text))


def downgrade() -> None:
    with op.batch_alter_table("inventory_count_line") as batch:
        batch.drop_column("reason")
