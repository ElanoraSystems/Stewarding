"""a role can be limited to certain parts of the dashboard

Revision ID: w7e1a5c9f3d6
Revises: v6d0f4b8e2c5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w7e1a5c9f3d6"
down_revision: Union[str, Sequence[str], None] = "v6d0f4b8e2c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("role", sa.Column("dashboard", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("role", "dashboard")
