"""rejection of a monitoring reading by a reviewer

Revision ID: a7b3d9f1c5e8
Revises: f6a2c8e0b5d7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b3d9f1c5e8"
down_revision: Union[str, Sequence[str], None] = "f6a2c8e0b5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.add_column(sa.Column("rejected_by", sa.Integer))
        batch.add_column(sa.Column("rejected_at", sa.DateTime))
        batch.add_column(sa.Column("reject_reason", sa.String(300)))
        batch.create_foreign_key("fk_reading_rejected_by", "user", ["rejected_by"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.drop_constraint("fk_reading_rejected_by", type_="foreignkey")
        batch.drop_column("reject_reason")
        batch.drop_column("rejected_at")
        batch.drop_column("rejected_by")
