"""face template on employees and the match distance kept with each punch

Revision ID: f6a2c8e0b5d7
Revises: e5f1b7d9a4c6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a2c8e0b5d7"
down_revision: Union[str, Sequence[str], None] = "e5f1b7d9a4c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("employee") as batch:
        batch.add_column(sa.Column("face_descriptor", sa.JSON))
        batch.add_column(sa.Column("face_enrolled_at", sa.DateTime))
    with op.batch_alter_table("attendance_record") as batch:
        batch.add_column(sa.Column("check_in_face", sa.Float))
        batch.add_column(sa.Column("check_out_face", sa.Float))


def downgrade() -> None:
    """Enrolled face templates are dropped."""
    with op.batch_alter_table("attendance_record") as batch:
        batch.drop_column("check_out_face")
        batch.drop_column("check_in_face")
    with op.batch_alter_table("employee") as batch:
        batch.drop_column("face_enrolled_at")
        batch.drop_column("face_descriptor")
