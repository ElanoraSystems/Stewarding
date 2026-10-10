"""general monitoring: any parameter, unit, frequency and reference on a check

Revision ID: a3f1c7d92b10
Revises: 92be1edbdd16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f1c7d92b10"
down_revision: Union[str, Sequence[str], None] = "92be1edbdd16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_TYPES = {"dishwasher": "Dishwasher", "glasswasher": "Glasswasher"}
MONITORING_TYPES = ['Cold storage', 'Defrosting', 'Cooking', 'Reheating', 'Cooling', 'Hot holding', 'Sanitising', 'Dishwasher', 'Glasswasher', 'Traceability', 'Calibration', 'Other']


def upgrade() -> None:
    equipment = sa.table("equipment", sa.column("kind", sa.String))
    for old, new in OLD_TYPES.items():
        op.execute(equipment.update().where(equipment.c.kind == old).values(kind=new))
    lookups = sa.table("lookup_value", sa.column("kind", sa.String), sa.column("value", sa.String),
                       sa.column("value_key", sa.String), sa.column("active", sa.Boolean))
    present = {k for (k,) in op.get_bind().execute(sa.select(lookups.c.value_key).where(lookups.c.kind == "monitoring_type"))}
    op.bulk_insert(lookups, [{"kind": "monitoring_type", "value": v, "value_key": v.lower(), "active": True}
                             for v in MONITORING_TYPES if v.lower() not in present])
    with op.batch_alter_table("equipment") as batch:
        batch.alter_column("kind", existing_type=sa.String(20), type_=sa.String(40))
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.add_column(sa.Column("parameter", sa.String(60), nullable=False, server_default="Temperature"))
        batch.add_column(sa.Column("unit", sa.String(20), server_default="°C"))
        batch.add_column(sa.Column("value_type", sa.String(10), nullable=False, server_default="number"))
        batch.add_column(sa.Column("require_reference", sa.Boolean, nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("weekdays", sa.String(20)))
        batch.add_column(sa.Column("day_of_month", sa.Integer))
        batch.alter_column("stage", existing_type=sa.String(40), type_=sa.String(60))
        batch.alter_column("min_temp_c", new_column_name="min_value", existing_type=sa.Numeric(5, 1), type_=sa.Numeric(10, 2))
        batch.alter_column("max_temp_c", new_column_name="max_value", existing_type=sa.Numeric(5, 1), type_=sa.Numeric(10, 2))
    with op.batch_alter_table("temperature_reading") as batch:
        batch.add_column(sa.Column("parameter", sa.String(60), nullable=False, server_default="Temperature"))
        batch.add_column(sa.Column("unit", sa.String(20), server_default="°C"))
        batch.add_column(sa.Column("value_type", sa.String(10), nullable=False, server_default="number"))
        batch.add_column(sa.Column("reference", sa.String(120)))
        batch.alter_column("stage", existing_type=sa.String(40), type_=sa.String(60))
        batch.alter_column("temp_c", new_column_name="value", existing_type=sa.Numeric(5, 1), type_=sa.Numeric(10, 2))
        batch.alter_column("min_limit", existing_type=sa.Numeric(5, 1), type_=sa.Numeric(10, 2))
        batch.alter_column("max_limit", existing_type=sa.Numeric(5, 1), type_=sa.Numeric(10, 2))


def downgrade() -> None:
    """Structural only: checks that are not temperature keep their numbers but lose the parameter and unit."""
    op.execute(sa.text("DELETE FROM lookup_value WHERE kind = 'monitoring_type'"))
    with op.batch_alter_table("temperature_reading") as batch:
        batch.alter_column("value", new_column_name="temp_c", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(5, 1))
        batch.alter_column("min_limit", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(5, 1))
        batch.alter_column("max_limit", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(5, 1))
        batch.alter_column("stage", existing_type=sa.String(60), type_=sa.String(40))
        for column in ("reference", "value_type", "unit", "parameter"):
            batch.drop_column(column)
    with op.batch_alter_table("equipment_schedule") as batch:
        batch.alter_column("min_value", new_column_name="min_temp_c", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(5, 1))
        batch.alter_column("max_value", new_column_name="max_temp_c", existing_type=sa.Numeric(10, 2), type_=sa.Numeric(5, 1))
        batch.alter_column("stage", existing_type=sa.String(60), type_=sa.String(40))
        for column in ("day_of_month", "weekdays", "require_reference", "value_type", "unit", "parameter"):
            batch.drop_column(column)
    with op.batch_alter_table("equipment") as batch:
        batch.alter_column("kind", existing_type=sa.String(40), type_=sa.String(20))
