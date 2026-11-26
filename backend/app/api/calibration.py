from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import Notification, Probe, ProbeCalibration, TemperatureReading, User
from ..pagination import row
from ..permissions import MANAGER, SUPERVISOR
from ..services import calibration as rules
from ..services.notify import notify, recipients
from ..services.reference import user_names
from .uploads import is_valid_evidence

router = APIRouter(prefix="/api/calibration", tags=["calibration"])

KINDS = "^(probe|infrared|data_logger)$"
PROBE_FIELDS = ("id", "code", "name", "kind", "location_id", "serial_number", "active")
CALIBRATION_FIELDS = ("id", "probe_id", "calibrated_at", "calibrated_by", "method", "reference_c", "reading_c", "tolerance_c", "passed", "comment", "evidence_path")


class ProbeIn(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=120)
    kind: str = Field(default="probe", pattern=KINDS)
    location_id: int
    serial_number: str | None = Field(default=None, max_length=80)


class ProbeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: str | None = Field(default=None, pattern=KINDS)
    serial_number: str | None = Field(default=None, max_length=80)
    active: bool | None = None


class CalibrationIn(BaseModel):
    method: Literal["ice_point", "boiling_point", "reference"]
    reading_c: Decimal = Field(ge=-100, le=400)
    reference_c: Decimal | None = Field(default=None, ge=-100, le=400)  # only for a check against another reference
    comment: str | None = Field(default=None, max_length=500)
    evidence_path: str | None = None

    @model_validator(mode="after")
    def _reference(self):
        if self.method == "reference" and self.reference_c is None:
            raise ValueError("Give the reference temperature")
        return self


def _probe(db: Session, user: User, probe_id: int) -> Probe:
    probe = db.get(Probe, probe_id)
    if not probe:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Probe not found")
    check_location(user, db, probe.location_id)
    return probe


def _since_last_pass(db: Session, probe: Probe) -> int:
    """Readings taken with this probe since its last good check: the ones to review when it turns out to be out."""
    good = db.scalar(select(func.max(ProbeCalibration.calibrated_at)).where(ProbeCalibration.probe_id == probe.id, ProbeCalibration.passed.is_(True)))
    stmt = select(func.count()).select_from(TemperatureReading).where(TemperatureReading.probe_id == probe.id, TemperatureReading.rejected_at.is_(None))
    return db.scalar(stmt.where(TemperatureReading.recorded_at > good) if good else stmt) or 0


def _view(db: Session, probe: Probe, now, names: dict) -> dict:
    last = rules.latest(db, probe.id)
    out = {**row(probe, *PROBE_FIELDS), **rules.status_of(db, probe, now, last), "last": None}
    out["readings_to_review"] = _since_last_pass(db, probe) if out["status"] == "failed" else 0
    out["due_at"] = out["due_at"].isoformat() + "Z" if out["due_at"] else None
    if last:
        out["last"] = {**row(last, *CALIBRATION_FIELDS), "by": names.get(last.calibrated_by, "")}
    return out


@router.get("/probes")
def list_probes(location_id: int | None = None, all: bool = False, user: User = Depends(require("temp.view")), db: Session = Depends(get_db)):
    """Every probe in the user's locations with where its calibration stands; the ones needing attention come first."""
    stmt = select(Probe).order_by(Probe.code)
    if location_id is not None:
        check_location(user, db, location_id)
        stmt = stmt.where(Probe.location_id == location_id)
    elif (allowed := scoped_locations(user, db)) is not None:
        stmt = stmt.where(Probe.location_id.in_(allowed))
    if not all:
        stmt = stmt.where(Probe.active.is_(True))
    now, names = timeutil.utc_now(), user_names(db)
    out = [_view(db, p, now, names) for p in db.scalars(stmt)]
    rank = {"failed": 0, "overdue": 1, "never": 2, "due_soon": 3, "ok": 4}
    return sorted(out, key=lambda p: (not p["active"], rank[p["status"]], p["code"]))


@router.post("/probes", status_code=201)
def create_probe(body: ProbeIn, user: User = Depends(require("equipment.manage")), db: Session = Depends(get_db)):
    check_location(user, db, body.location_id)
    code = body.code.strip().upper()
    if db.scalar(select(Probe.id).where(Probe.code == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A probe with this code already exists")
    probe = Probe(**{**body.model_dump(), "code": code, "name": " ".join(body.name.split())})
    db.add(probe)
    db.flush()
    audit(db, user, "probe.create", "probe", probe.id, None, {"code": code})
    db.commit()
    return _view(db, probe, timeutil.utc_now(), user_names(db))


@router.put("/probes/{probe_id}")
def update_probe(probe_id: int, body: ProbeUpdate, user: User = Depends(require("equipment.manage")), db: Session = Depends(get_db)):
    probe = _probe(db, user, probe_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(probe, key, value)
    audit(db, user, "probe.update", "probe", probe.id, None, changes)
    db.commit()
    return _view(db, probe, timeutil.utc_now(), user_names(db))


@router.get("/probes/{probe_id}/calibrations")
def history(probe_id: int, user: User = Depends(require("temp.view")), db: Session = Depends(get_db)):
    probe = _probe(db, user, probe_id)
    names = user_names(db)
    rows = db.scalars(select(ProbeCalibration).where(ProbeCalibration.probe_id == probe.id)
                      .order_by(ProbeCalibration.calibrated_at.desc(), ProbeCalibration.id.desc()).limit(100))
    return [{**row(c, *CALIBRATION_FIELDS), "by": names.get(c.calibrated_by, ""), "deviation": c.reading_c - c.reference_c} for c in rows]


@router.post("/probes/{probe_id}/calibrations", status_code=201)
def calibrate(probe_id: int, body: CalibrationIn, user: User = Depends(require("temp.record")), db: Session = Depends(get_db)):
    probe = _probe(db, user, probe_id)
    if not probe.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This probe is not in use")
    if body.evidence_path and not is_valid_evidence(body.evidence_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown photo file")
    reference, passed = rules.judge(body.method, body.reference_c, body.reading_c, rules.TOLERANCE_C)
    note = (body.comment or "").strip()
    if not passed and len(note) < 5:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The probe is out by more than 1 °C. Say what was done about it (at least 5 characters)")
    now = timeutil.utc_now()
    entry = ProbeCalibration(probe_id=probe.id, calibrated_at=now, calibrated_by=user.id, method=body.method, reference_c=reference,
                             reading_c=body.reading_c, tolerance_c=rules.TOLERANCE_C, passed=passed, comment=note or None, evidence_path=body.evidence_path)
    db.add(entry)
    db.flush()
    audit(db, user, "probe.calibrate", "probe", probe.id, None, {"passed": passed, "method": body.method})
    if passed:  # the reminders for this probe have done their job
        db.execute(update(Notification).where(Notification.dedupe_key.like(f"probe_%:{probe.id}:%"), Notification.resolved_at.is_(None))
                   .values(resolved_at=now, read_at=now))
    else:
        taken = _since_last_pass(db, probe)
        notify(db, recipients(db, probe.location_id, SUPERVISOR, MANAGER, category="monitoring"), "probe_failed",
               f"Probe failed calibration: {probe.name} ({probe.code})", key=f"probe_fail:{entry.id}", priority="critical",
               location_id=probe.location_id, link="/calibration", requires_ack=True,
               body=f"Read {body.reading_c.normalize():f} °C against {reference.normalize():f} °C. Do not use it for readings until it passes."
                    + (f" {taken} reading{'s' if taken != 1 else ''} taken with it since its last good check need reviewing." if taken else "") + f" {note}")
    db.commit()
    return _view(db, probe, now, user_names(db))
