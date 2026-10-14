"""custom roles: a tier, a label and a built-in flag on each role

Revision ID: f2a8c4e6b0d3
Revises: e1f7b3d5a9c2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a8c4e6b0d3"
down_revision: Union[str, Sequence[str], None] = "e1f7b3d5a9c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

role = sa.table("role", sa.column("name", sa.String), sa.column("tier", sa.String), sa.column("builtin", sa.Boolean))


def upgrade() -> None:
    with op.batch_alter_table("role") as batch:
        batch.add_column(sa.Column("label", sa.String(80)))
        batch.add_column(sa.Column("tier", sa.String(20), nullable=False, server_default="steward"))
        batch.add_column(sa.Column("builtin", sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute(role.update().where(role.c.name.in_(["manager", "supervisor", "steward"])).values(tier=role.c.name, builtin=True))


def downgrade() -> None:
    with op.batch_alter_table("role") as batch:
        batch.drop_column("builtin")
        batch.drop_column("tier")
        batch.drop_column("label")
