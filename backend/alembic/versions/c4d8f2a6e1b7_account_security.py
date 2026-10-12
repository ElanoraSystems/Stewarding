"""password change on first sign-in, session versioning and last sign-in

Revision ID: c4d8f2a6e1b7
Revises: b7e2d4a1c9f3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4d8f2a6e1b7"
down_revision: Union[str, Sequence[str], None] = "b7e2d4a1c9f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch:
        batch.add_column(sa.Column("must_change_password", sa.Boolean, nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("token_version", sa.Integer, nullable=False, server_default="0"))
        batch.add_column(sa.Column("last_login_at", sa.DateTime))


def downgrade() -> None:
    with op.batch_alter_table("user") as batch:
        for column in ("last_login_at", "token_version", "must_change_password"):
            batch.drop_column(column)
