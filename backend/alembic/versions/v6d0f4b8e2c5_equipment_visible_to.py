"""monitoring points can be limited to certain roles

Revision ID: v6d0f4b8e2c5
Revises: u5c9e3a7d1b4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v6d0f4b8e2c5"
down_revision: Union[str, Sequence[str], None] = "u5c9e3a7d1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("equipment", sa.Column("visible_to", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("equipment", "visible_to")
