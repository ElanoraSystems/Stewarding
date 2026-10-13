"""organization or company name on employees

Revision ID: e5f1b7d9a4c6
Revises: d4e0a6c8f3b5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f1b7d9a4c6"
down_revision: Union[str, Sequence[str], None] = "d4e0a6c8f3b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("employee") as batch:
        batch.add_column(sa.Column("company", sa.String(120)))


def downgrade() -> None:
    with op.batch_alter_table("employee") as batch:
        batch.drop_column("company")
