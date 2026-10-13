"""text and dropdown fields on monitoring checks

Revision ID: d5a9b3e7c2f1
Revises: c4d8f2a6e1b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5a9b3e7c2f1"
down_revision: Union[str, Sequence[str], None] = "c4d8f2a6e1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.add_column(sa.Column("options", sa.JSON))
        batch.add_column(sa.Column("fail_options", sa.JSON))
        batch.add_column(sa.Column("max_length", sa.Integer))
    with op.batch_alter_table("temperature_reading") as batch:
        batch.add_column(sa.Column("answer", sa.String(500)))
        batch.alter_column("value", existing_type=sa.Numeric(10, 2), nullable=True)


def downgrade() -> None:
    """Structural only: written and chosen answers are dropped and their readings keep a value of zero."""
    op.execute(sa.text("UPDATE temperature_reading SET value = 0 WHERE value IS NULL"))
    with op.batch_alter_table("temperature_reading") as batch:
        batch.alter_column("value", existing_type=sa.Numeric(10, 2), nullable=False)
        batch.drop_column("answer")
    with op.batch_alter_table("equipment_schedule") as batch:
        for column in ("max_length", "fail_options", "options"):
            batch.drop_column(column)
