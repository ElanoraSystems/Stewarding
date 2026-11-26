"""an attendance record can say its shift was worked out from the check-in time

Revision ID: f2c5a7d9e1b4
Revises: e1b4f6c8d0a3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2c5a7d9e1b4"
down_revision: Union[str, Sequence[str], None] = "e1b4f6c8d0a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attendance_record", sa.Column("shift_inferred", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("attendance_record") as batch:
        batch.drop_column("shift_inferred")
