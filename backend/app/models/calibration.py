from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .core import ts


class Probe(Base):
    """A thermometer or probe used for food safety readings, which has to be checked against a known temperature at regular intervals."""

    __tablename__ = "probe"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="probe")  # probe | infrared | data_logger
    location_id: Mapped[int] = mapped_column(ForeignKey("location.id"), index=True)
    serial_number: Mapped[str | None] = mapped_column(String(80))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = ts()


class ProbeCalibration(Base):
    """One check of a probe: what it read against what it should (ice water is 0 °C, boiling water 100 °C), and whether it is within tolerance."""

    __tablename__ = "probe_calibration"
    id: Mapped[int] = mapped_column(primary_key=True)
    probe_id: Mapped[int] = mapped_column(ForeignKey("probe.id"), index=True)
    calibrated_at: Mapped[datetime] = ts(index=True)
    calibrated_by: Mapped[int] = mapped_column(ForeignKey("user.id"))
    method: Mapped[str] = mapped_column(String(20))  # ice_point | boiling_point | reference
    reference_c: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    reading_c: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    tolerance_c: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    passed: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)  # what was done when it failed: adjusted, replaced, taken out of use
    evidence_path: Mapped[str | None] = mapped_column(String(300))
