"""checklists can be limited to certain roles

Revision ID: x8f2b6d0a4e7
Revises: w7e1a5c9f3d6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x8f2b6d0a4e7"
down_revision: Union[str, Sequence[str], None] = "w7e1a5c9f3d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("checklist_template", sa.Column("visible_to", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("checklist_template", "visible_to")
