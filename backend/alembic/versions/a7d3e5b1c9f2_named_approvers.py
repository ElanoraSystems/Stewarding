"""named approvers on a checklist and on a monitoring log

Revision ID: a7d3e5b1c9f2
Revises: d7f1c3e9a5b6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7d3e5b1c9f2"
down_revision: Union[str, Sequence[str], None] = "d7f1c3e9a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("checklist_template", sa.Column("approvers", sa.JSON(), nullable=True))
    op.add_column("equipment", sa.Column("approvers", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("equipment") as batch:
        batch.drop_column("approvers")
    with op.batch_alter_table("checklist_template") as batch:
        batch.drop_column("approvers")
