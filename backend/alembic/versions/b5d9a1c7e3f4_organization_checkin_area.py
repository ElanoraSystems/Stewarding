"""one check-in area for the whole organization instead of one per location

Revision ID: b5d9a1c7e3f4
Revises: a1c5e9b3d7f2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5d9a1c7e3f4"
down_revision: Union[str, Sequence[str], None] = "a1c5e9b3d7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("organization") as batch:
        batch.add_column(sa.Column("latitude", sa.Float))
        batch.add_column(sa.Column("longitude", sa.Float))
        batch.add_column(sa.Column("geofence_radius_m", sa.Integer))
    bind = op.get_bind()
    first = bind.execute(sa.text(
        "SELECT latitude, longitude, geofence_radius_m FROM location WHERE geofence_radius_m IS NOT NULL ORDER BY id LIMIT 1")).first()
    if first:  # keep an area somebody had already set: the first location's becomes the organization's
        exists = bind.execute(sa.text("SELECT 1 FROM organization WHERE id = 1")).first()
        if exists:
            bind.execute(sa.text("UPDATE organization SET latitude = :a, longitude = :b, geofence_radius_m = :r WHERE id = 1"),
                         {"a": first[0], "b": first[1], "r": first[2]})
        else:
            bind.execute(sa.text("INSERT INTO organization (id, name, timezone, latitude, longitude, geofence_radius_m) VALUES (1, '', 'Asia/Kuwait', :a, :b, :r)"),
                         {"a": first[0], "b": first[1], "r": first[2]})
    with op.batch_alter_table("location") as batch:
        batch.drop_column("geofence_radius_m")
        batch.drop_column("longitude")
        batch.drop_column("latitude")


def downgrade() -> None:
    """The organization's area goes back onto every location."""
    with op.batch_alter_table("location") as batch:
        batch.add_column(sa.Column("latitude", sa.Float))
        batch.add_column(sa.Column("longitude", sa.Float))
        batch.add_column(sa.Column("geofence_radius_m", sa.Integer))
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE location SET latitude = (SELECT latitude FROM organization WHERE id = 1), "
                         "longitude = (SELECT longitude FROM organization WHERE id = 1), "
                         "geofence_radius_m = (SELECT geofence_radius_m FROM organization WHERE id = 1)"))
    with op.batch_alter_table("organization") as batch:
        batch.drop_column("geofence_radius_m")
        batch.drop_column("longitude")
        batch.drop_column("latitude")
