from datetime import datetime

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..db import Base
from .core import ts


class HaccpPlan(Base):
    """The written part of the HACCP plan (scope, team, hazard analysis, review), one row for the organization. The control points come from the monitoring points."""

    __tablename__ = "haccp_plan"
    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    updated_at: Mapped[datetime] = ts()


class HaccpPlanVersion(Base):
    """A version of the plan that has been superseded, kept exactly as it was so it can be opened, printed and restored."""

    __tablename__ = "haccp_plan_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    content: Mapped[dict] = mapped_column(JSON)
    saved_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))
    saved_at: Mapped[datetime] = ts()
