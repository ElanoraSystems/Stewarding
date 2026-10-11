from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import Employee, User
from ..services import exporters
from ..services.records import KINDS, build_record
from ..services.reports import PERIODS, REPORTS, build_report

router = APIRouter(prefix="/api/reports", tags=["reports"])

MEDIA = {"csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "pdf": "application/pdf"}
RENDER = {"csv": exporters.to_csv, "xlsx": exporters.to_xlsx, "pdf": exporters.to_pdf}
RECORD_RENDER = {"csv": exporters.record_to_csv, "xlsx": exporters.record_to_xlsx, "pdf": exporters.record_to_pdf}


def _build(db: Session, user: User, period: str, anchor: date | None, location_id: int | None,
           employee_id: int | None) -> dict:
    if period not in PERIODS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown report period")
    if location_id is not None:
        check_location(user, db, location_id)
    try:
        return build_report(db, timeutil.utc_now(), scoped_locations(user, db), period, anchor, location_id, employee_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


def _record(db: Session, user: User, kind: str, date_from: date | None, date_to: date | None, location_id: int | None,
            equipment_id: int | None) -> dict:
    if kind not in KINDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown record type")
    if location_id is not None:
        check_location(user, db, location_id)
    now = timeutil.utc_now()
    day_to = date_to or now.date()
    day_from = date_from or day_to
    name = db.scalar(select(Employee.full_name).where(Employee.user_id == user.id)) or user.email
    try:
        return build_record(db, now, scoped_locations(user, db), kind, day_from, day_to, location_id, equipment_id, name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


@router.get("/records/{kind}")
def record(kind: str, date_from: date | None = None, date_to: date | None = None, location_id: int | None = None,
           equipment_id: int | None = None, user: User = Depends(require("report.view")), db: Session = Depends(get_db)):
    return _record(db, user, kind, date_from, date_to, location_id, equipment_id)


@router.get("/records/{kind}/export")
def export_record(kind: str, fmt: Literal["csv", "xlsx", "pdf"] = "pdf", date_from: date | None = None,
                  date_to: date | None = None, location_id: int | None = None, equipment_id: int | None = None,
                  user: User = Depends(require("report.export")), db: Session = Depends(get_db)):
    doc = _record(db, user, kind, date_from, date_to, location_id, equipment_id)
    audit(db, user, "report.export", "record", None, None, {"kind": kind, "format": fmt, "from": doc["period"]["from"],
                                                           "to": doc["period"]["to"], "location_id": location_id})
    db.commit()
    filename = f"{kind}-record-{doc['period']['from']}-to-{doc['period']['to']}.{fmt}"
    return Response(RECORD_RENDER[fmt](doc), media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("")
def catalog(user: User = Depends(require("report.view"))):
    return {p: [fn.__name__.removeprefix("sec_") for fn in REPORTS[p]] for p in PERIODS}


@router.get("/{period}")
def report(period: str, anchor: date | None = None, location_id: int | None = None, employee_id: int | None = None,
           user: User = Depends(require("report.view")), db: Session = Depends(get_db)):
    return _build(db, user, period, anchor, location_id, employee_id)


@router.get("/{period}/export")
def export(period: str, fmt: Literal["csv", "xlsx", "pdf"] = "xlsx", anchor: date | None = None,
           location_id: int | None = None, employee_id: int | None = None,
           user: User = Depends(require("report.export")), db: Session = Depends(get_db)):
    data = _build(db, user, period, anchor, location_id, employee_id)
    audit(db, user, "report.export", "report", None, None, {"period": period, "format": fmt, "from": data["period"]["from"],
                                                           "to": data["period"]["to"], "location_id": location_id})
    db.commit()
    filename = f"stewarding-{period}-{data['period']['from']}.{fmt}"
    return Response(RENDER[fmt](data), media_type=MEDIA[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
