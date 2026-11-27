"""the written part of the HACCP plan and its earlier versions

Revision ID: h4e7c9a1b3d6
Revises: g3d6b8e0f2c5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h4e7c9a1b3d6"
down_revision: Union[str, Sequence[str], None] = "g3d6b8e0f2c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "haccp_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "haccp_plan_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("saved_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("haccp_plan_version")
    op.drop_table("haccp_plan")
