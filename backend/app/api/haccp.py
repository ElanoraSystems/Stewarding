from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import timeutil
from ..audit import audit
from ..db import get_db
from ..deps import check_location, require, scoped_locations
from ..models import HaccpPlan, HaccpPlanVersion, User
from ..services import exporters, haccp
from ..services.organization import report_identity, stamp
from ..services.reference import user_names
from .reports import MEDIA, _author

router = APIRouter(prefix="/api/haccp", tags=["haccp"])


class HazardIn(BaseModel):
    hazard: str = Field(min_length=2, max_length=400)
    kind: Literal["Biological", "Chemical", "Physical", "Allergen"]
    significant: bool = False
    control: str = Field(min_length=2, max_length=600)
    basis: str = Field(default="", max_length=300)  # why it is or is not significant: how severe, how likely


class StepIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)  # a decision's name is its question
    kind: Literal["step", "decision"] = "step"
    control: Literal["", "CCP", "OPRP"] = ""
    no_action: str = Field(default="", max_length=120)  # a decision: what happens when the answer is no ('yes' goes on to the next step)
    hazards: list[HazardIn] = Field(default_factory=list, max_length=10)
    no_hazard: str = Field(default="", max_length=200)  # why a step with no hazard has none

    @model_validator(mode="after")
    def _agree(self):
        """The flow and the hazard analysis are one list, so a step cannot be in the flow without being analysed."""
        if self.kind == "decision" and len(self.no_action.strip()) < 3:
            raise ValueError(f"'{self.name}' is a decision: say what happens when the answer is no")
        if self.kind == "step":
            self.no_action = ""
        if not self.hazards and len(self.no_hazard.strip()) < 3:
            raise ValueError(f"'{self.name}' needs at least one hazard, or a note saying why it has none")
        if self.control and not any(h.significant for h in self.hazards):
            raise ValueError(f"'{self.name}' is a {self.control} step, so it needs a significant hazard that it controls")
        return self


class ProcessIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    references: str = Field(default="", max_length=300)  # the Codex texts and local rules this flow was written against
    confirmed_on: str = Field(default="", max_length=30)  # the flow checked against the real operation, on site
    confirmed_by: str = Field(default="", max_length=120)
    steps: list[StepIn] = Field(default_factory=list, max_length=60)  # in order; the chart wraps after five to a row and continues on the next page


class PlanIn(BaseModel):
    owner: str = Field(default="", max_length=120)
    team: str = Field(default="", max_length=1000)
    scope: str = Field(default="", max_length=2000)
    products: str = Field(default="", max_length=2000)
    review: str = Field(default="", max_length=1000)
    processes: list[ProcessIn] = Field(default_factory=list, max_length=12)  # one flow, with its hazard analysis, per kind of food
    new_version: bool = False  # the old version is kept exactly as it was and this one is numbered one higher
    note: str = Field(default="", max_length=200)  # what changed, required with a new version

    @model_validator(mode="after")
    def _names(self):
        names = [" ".join(p.name.split()).casefold() for p in self.processes]
        if len(set(names)) != len(names):
            raise ValueError("Two processes have the same name")
        return self


def _out(db: Session) -> dict:
    content, version, plan = haccp.load(db)
    return {**content, "version": version or 1, "saved": plan is not None, "updated_at": plan.updated_at.isoformat() + "Z" if plan else None}


def _keep_current(db: Session, plan: HaccpPlan) -> None:
    """Keeps the version about to be replaced exactly as it is, so it can still be opened, printed and restored."""
    if db.scalar(select(HaccpPlanVersion.id).where(HaccpPlanVersion.version == plan.version)) is None:
        db.add(HaccpPlanVersion(version=plan.version, content=plan.content, saved_by=plan.updated_by, saved_at=plan.updated_at))


def _write(db: Session, user: User, body_content: dict, new_version: bool, note: str, action: str) -> dict:
    content, version, plan = haccp.load(db)
    now = timeutil.utc_now()
    name, _ = _author(db, user)
    revisions = list(content["revisions"])
    if plan is None:
        version = 1
        revisions.append({"version": 1, "date": now.strftime("%d %b %Y"), "by": name, "note": note.strip() or "First version"})
    elif new_version:
        _keep_current(db, plan)
        version += 1
        revisions.append({"version": version, "date": now.strftime("%d %b %Y"), "by": name, "note": note.strip()})
    new = {**body_content, "revisions": revisions}
    if plan is None:
        db.add(HaccpPlan(content=new, version=version, updated_by=user.id))
    else:
        plan.content, plan.version, plan.updated_by, plan.updated_at = new, version, user.id, now
    audit(db, user, action, "haccp_plan", None, None, {"version": version, "new_version": new_version, "note": note.strip()})
    db.commit()
    return _out(db)


@router.get("/plan")
def get_plan(user: User = Depends(require("equipment.view")), db: Session = Depends(get_db)):
    return _out(db)


@router.put("/plan")
def save_plan(body: PlanIn, user: User = Depends(require("equipment.manage")), db: Session = Depends(get_db)):
    if body.new_version and len(body.note.strip()) < 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Say what changed in this version")
    content = {"owner": body.owner.strip(), "team": body.team.strip(), "scope": body.scope.strip(), "products": body.products.strip(), "review": body.review.strip() or haccp.REVIEW,
               "processes": [{**p.model_dump(exclude={"steps", "name"}), "name": " ".join(p.name.split()), "steps": [st.model_dump() for st in p.steps]} for p in body.processes]}
    return _write(db, user, content, body.new_version, body.note, "haccp.save")


@router.get("/plan/versions")
def versions(user: User = Depends(require("equipment.view")), db: Session = Depends(get_db)):
    """The current version and every earlier one, newest first, with who last changed it and when."""
    content, current, plan = haccp.load(db)
    names = user_names(db)
    notes = {r["version"]: r["note"] for r in content["revisions"]}
    rows = [{"version": current or 1, "current": True, "saved_at": plan.updated_at.isoformat() + "Z" if plan else None, "by": names.get(plan.updated_by, "") if plan else "", "note": notes.get(current or 1, "")}]
    for v in db.scalars(select(HaccpPlanVersion).order_by(HaccpPlanVersion.version.desc())):
        rows.append({"version": v.version, "current": False, "saved_at": v.saved_at.isoformat() + "Z", "by": names.get(v.saved_by, ""), "note": notes.get(v.version, "")})
    return rows


@router.get("/plan/versions/{version}")
def one_version(version: int, user: User = Depends(require("equipment.view")), db: Session = Depends(get_db)):
    try:
        content, number = haccp.content_of(db, version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    return {**content, "version": number}


@router.post("/plan/versions/{version}/restore")
def restore(version: int, user: User = Depends(require("equipment.manage")), db: Session = Depends(get_db)):
    """An earlier version becomes the new current one under the next number; nothing is erased, so the version it replaces is kept too."""
    try:
        content, number = haccp.content_of(db, version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    current = haccp.load(db)[1] or 1
    if number == current:
        raise HTTPException(status.HTTP_409_CONFLICT, "That is already the current version")
    body = {k: content[k] for k in ("owner", "team", "scope", "products", "review", "processes")}
    return _write(db, user, body, True, f"Restored from version {number}", "haccp.restore")


@router.get("/plan/pdf")
def plan_pdf(location_id: int | None = None, version: int | None = None, user: User = Depends(require("equipment.view")), db: Session = Depends(get_db)):
    """The plan as a PDF for one outlet or all the outlets this person may see: the current version, or an earlier one."""
    if location_id is not None:
        check_location(user, db, location_id)
    now = timeutil.utc_now()
    name, position = _author(db, user)
    try:
        doc = haccp.build_plan(db, now, scoped_locations(user, db), location_id, name, version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    identity = report_identity(db)
    doc = {**doc, "prepared_position": position, "generated_at": stamp(now, identity["timezone"]), "organization": identity}
    audit(db, user, "report.export", "haccp_plan", None, None, {"format": "pdf", "location_id": location_id, "version": version})
    db.commit()
    return Response(exporters.record_to_pdf(doc), media_type=MEDIA["pdf"], headers={"Content-Disposition": f'attachment; filename="haccp-plan-v{doc["period"]["label"].split()[-1]}.pdf"'})
