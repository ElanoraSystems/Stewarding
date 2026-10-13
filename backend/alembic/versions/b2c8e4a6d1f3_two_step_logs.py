"""time in and time out logs, and a named reference on monitoring checks

Revision ID: b2c8e4a6d1f3
Revises: a1e7f3c9d5b2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c8e4a6d1f3"
down_revision: Union[str, Sequence[str], None] = "a1e7f3c9d5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.add_column(sa.Column("reference_label", sa.String(40)))
        batch.add_column(sa.Column("phase", sa.String(10)))
    with op.batch_alter_table("temperature_reading") as batch:
        batch.add_column(sa.Column("start_reading_id", sa.Integer))
        batch.create_foreign_key("fk_reading_start_reading", "temperature_reading", ["start_reading_id"], ["id"])
        batch.create_index("ix_temperature_reading_start_reading_id", ["start_reading_id"])


def downgrade() -> None:
    with op.batch_alter_table("temperature_reading") as batch:
        batch.drop_index("ix_temperature_reading_start_reading_id")
        batch.drop_constraint("fk_reading_start_reading", type_="foreignkey")
        batch.drop_column("start_reading_id")
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.drop_column("phase")
        batch.drop_column("reference_label")
