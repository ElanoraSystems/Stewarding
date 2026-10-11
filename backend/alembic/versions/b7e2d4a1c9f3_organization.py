"""organization details and logo for report headers

Revision ID: b7e2d4a1c9f3
Revises: a3f1c7d92b10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2d4a1c9f3"
down_revision: Union[str, Sequence[str], None] = "a3f1c7d92b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("legal_name", sa.String(160)),
        sa.Column("address", sa.String(500)),
        sa.Column("phone", sa.String(40)),
        sa.Column("email", sa.String(120)),
        sa.Column("website", sa.String(200)),
        sa.Column("registration_number", sa.String(60)),
        sa.Column("report_footer", sa.String(300)),
        sa.Column("logo", sa.String(60)),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kuwait"),
    )


def downgrade() -> None:
    op.drop_table("organization")
