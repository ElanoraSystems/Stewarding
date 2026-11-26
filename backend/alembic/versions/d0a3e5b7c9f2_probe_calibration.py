"""probes and their calibration checks

Revision ID: d0a3e5b7c9f2
Revises: c9f2d4a6b8e1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0a3e5b7c9f2"
down_revision: Union[str, Sequence[str], None] = "c9f2d4a6b8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "probe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id"), nullable=False),
        sa.Column("serial_number", sa.String(80)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_probe_location_id", "probe", ["location_id"])
    op.create_table(
        "probe_calibration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("probe_id", sa.Integer(), sa.ForeignKey("probe.id"), nullable=False),
        sa.Column("calibrated_at", sa.DateTime(), nullable=False),
        sa.Column("calibrated_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("reference_c", sa.Numeric(6, 2), nullable=False),
        sa.Column("reading_c", sa.Numeric(6, 2), nullable=False),
        sa.Column("tolerance_c", sa.Numeric(4, 2), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("evidence_path", sa.String(300)),
    )
    op.create_index("ix_probe_calibration_probe_id", "probe_calibration", ["probe_id"])
    op.create_index("ix_probe_calibration_calibrated_at", "probe_calibration", ["calibrated_at"])


def downgrade() -> None:
    op.drop_table("probe_calibration")
    op.drop_table("probe")
