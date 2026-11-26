"""a monitoring point has a control level: PRP, operational PRP or critical control point

Revision ID: c9f2d4a6b8e1
Revises: b8e1c3f5a7d9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9f2d4a6b8e1"
down_revision: Union[str, Sequence[str], None] = "b8e1c3f5a7d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("equipment", sa.Column("control_level", sa.String(10), nullable=False, server_default="prp"))


def downgrade() -> None:
    with op.batch_alter_table("equipment") as batch:
        batch.drop_column("control_level")
