import logging
import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import timeutil
from .db import SessionLocal
from .models import Location
from .services import checklists
from .services.alerts import run_alerts

log = logging.getLogger("stewarding.scheduler")
INTERVAL_SECONDS = 60


def run_cycle(db: Session, now=None) -> dict:
    """One scheduler pass: generate today's tasks, flag overdue ones; idempotent."""
    now = now or timeutil.utc_now()
    created = 0
    for location in db.scalars(select(Location).where(Location.active.is_(True))):
        created += checklists.generate_for_location(db, location, now)
    overdue = checklists.mark_overdue(db, now)
    alerts = run_alerts(db, now)
    db.commit()
    return {"created": created, "overdue": overdue, "alerts": alerts}


def _loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                log.info("scheduler cycle %s", run_cycle(db))
        except Exception:
            log.exception("scheduler cycle failed")
        time.sleep(INTERVAL_SECONDS)


def start_background() -> None:
    threading.Thread(target=_loop, name="stewarding-scheduler", daemon=True).start()
