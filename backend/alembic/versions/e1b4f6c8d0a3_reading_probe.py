"""a reading can name the probe it was made with

Revision ID: e1b4f6c8d0a3
Revises: d0a3e5b7c9f2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1b4f6c8d0a3"
down_revision: Union[str, Sequence[str], None] = "d0a3e5b7c9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.add_column(sa.Column("probe_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_temperature_reading_probe", "probe", ["probe_id"], ["id"])
        batch.create_index("ix_temperature_reading_probe_id", ["probe_id"])


def downgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.drop_index("ix_temperature_reading_probe_id")
        batch.drop_constraint("fk_temperature_reading_probe", type_="foreignkey")
        batch.drop_column("probe_id")
