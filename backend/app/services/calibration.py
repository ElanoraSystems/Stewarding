from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Probe, ProbeCalibration
from .settings import get_setting

DUE_SOON_DAYS = 3
TOLERANCE_C = Decimal("1.0")  # a probe within one degree of the reference passes
REFERENCE_C = {"ice_point": Decimal("0"), "boiling_point": Decimal("100")}  # boiling is 100 °C at sea level; use "reference" at altitude
METHODS = ("ice_point", "boiling_point", "reference")


def latest(db: Session, probe_id: int) -> ProbeCalibration | None:
    return db.scalar(select(ProbeCalibration).where(ProbeCalibration.probe_id == probe_id)
                     .order_by(ProbeCalibration.calibrated_at.desc(), ProbeCalibration.id.desc()).limit(1))


def judge(method: str, reference: Decimal | None, reading: Decimal, tolerance: Decimal) -> tuple[Decimal, bool]:
    """The reference temperature used and whether the reading is close enough to it."""
    ref = REFERENCE_C.get(method, reference)
    if ref is None:
        raise ValueError("Give the reference temperature")
    return ref, abs(reading - ref) <= tolerance


def status_of(db: Session, probe: Probe, now: datetime, last: ProbeCalibration | None = None) -> dict:
    """never | failed | overdue | due_soon | ok, with when it is next due: a failed check keeps the probe out of use until a passing one."""
    last = last or latest(db, probe.id)
    if last is None:
        return {"status": "never", "due_at": None, "days_left": None}
    due = last.calibrated_at + timedelta(days=get_setting(db, "calibration.interval_days"))
    left = (due - now).total_seconds() / 86400
    if not last.passed:
        status = "failed"
    elif left < 0:
        status = "overdue"
    elif left <= DUE_SOON_DAYS:
        status = "due_soon"
    else:
        status = "ok"
    return {"status": status, "due_at": due, "days_left": int(left // 1)}


def usable(status: str) -> bool:
    """A probe may be used for readings only while its calibration is current."""
    return status in ("ok", "due_soon")
