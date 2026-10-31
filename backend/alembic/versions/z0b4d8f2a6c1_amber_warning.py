"""an amber warning zone on number checks, and a Frying oil monitoring type

Revision ID: z0b4d8f2a6c1
Revises: y9a3c7e1b5d2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z0b4d8f2a6c1"
down_revision: Union[str, Sequence[str], None] = "y9a3c7e1b5d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("equipment_schedule", sa.Column("warn_min", sa.Numeric(10, 2), nullable=True))
    op.add_column("equipment_schedule", sa.Column("warn_max", sa.Numeric(10, 2), nullable=True))
    op.add_column("temperature_reading", sa.Column("warning", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("INSERT INTO lookup_value (kind, value, value_key, active) SELECT 'monitoring_type', 'Frying oil', 'frying oil', "
               + ("TRUE" if op.get_bind().dialect.name == "postgresql" else "1")
               + " WHERE NOT EXISTS (SELECT 1 FROM lookup_value WHERE kind = 'monitoring_type' AND value_key = 'frying oil')")


def downgrade() -> None:
    op.drop_column("temperature_reading", "warning")
    op.drop_column("equipment_schedule", "warn_max")
    op.drop_column("equipment_schedule", "warn_min")
