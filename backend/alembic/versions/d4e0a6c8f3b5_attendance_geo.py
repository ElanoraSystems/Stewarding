"""position kept with each check-in and check-out

Revision ID: d4e0a6c8f3b5
Revises: c3d9f5b7e2a4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e0a6c8f3b5"
down_revision: Union[str, Sequence[str], None] = "c3d9f5b7e2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("attendance_record") as batch:
        batch.add_column(sa.Column("check_in_geo", sa.JSON))
        batch.add_column(sa.Column("check_out_geo", sa.JSON))


def downgrade() -> None:
    with op.batch_alter_table("attendance_record") as batch:
        batch.drop_column("check_out_geo")
        batch.drop_column("check_in_geo")
