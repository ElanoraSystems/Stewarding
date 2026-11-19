"""how late an overdue checklist task was when completed, and why

Revision ID: b8e1c3f5a7d9
Revises: a7d3e5b1c9f2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8e1c3f5a7d9"
down_revision: Union[str, Sequence[str], None] = "a7d3e5b1c9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("checklist_instance", sa.Column("late_minutes", sa.Integer(), nullable=True))
    op.add_column("checklist_instance", sa.Column("late_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("checklist_instance") as batch:
        batch.drop_column("late_reason")
        batch.drop_column("late_minutes")
