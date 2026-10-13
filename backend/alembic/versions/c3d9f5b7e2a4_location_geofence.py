"""replace the location check-in PIN with a geofence

Revision ID: c3d9f5b7e2a4
Revises: b2c8e4a6d1f3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d9f5b7e2a4"
down_revision: Union[str, Sequence[str], None] = "b2c8e4a6d1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("location") as batch:
        batch.drop_column("checkin_pin_hash")
        batch.add_column(sa.Column("latitude", sa.Float))
        batch.add_column(sa.Column("longitude", sa.Float))
        batch.add_column(sa.Column("geofence_radius_m", sa.Integer))


def downgrade() -> None:
    """Structural only: the PIN hashes are gone, so no location has a PIN after a downgrade."""
    with op.batch_alter_table("location") as batch:
        batch.drop_column("geofence_radius_m")
        batch.drop_column("longitude")
        batch.drop_column("latitude")
        batch.add_column(sa.Column("checkin_pin_hash", sa.String(100)))
