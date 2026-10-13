"""required or optional questions on monitoring forms

Revision ID: b8c4e0a2d6f9
Revises: a7b3d9f1c5e8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c4e0a2d6f9"
down_revision: Union[str, Sequence[str], None] = "a7b3d9f1c5e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.add_column(sa.Column("required", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.drop_column("required")
