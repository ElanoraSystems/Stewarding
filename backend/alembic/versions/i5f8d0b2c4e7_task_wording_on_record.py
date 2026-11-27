"""a completed checklist task keeps the wording it was ticked under

Revision ID: i5f8d0b2c4e7
Revises: h4e7c9a1b3d6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i5f8d0b2c4e7"
down_revision: Union[str, Sequence[str], None] = "h4e7c9a1b3d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("checklist_instance", sa.Column("task_text", sa.String(length=300), nullable=True))
    op.add_column("checklist_instance", sa.Column("task_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("checklist_instance") as batch:
        batch.drop_column("task_instructions")
        batch.drop_column("task_text")
