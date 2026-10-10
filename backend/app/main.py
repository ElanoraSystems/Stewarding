from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import scheduler
from .api import (attendance, audit, auth, breakage, checklists, dashboard, employees, equipment, inventory,
                  notifications, reports, roster, settings as settings_api, stock, temperature, uploads)
from .config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.scheduler_enabled:
        scheduler.start_background()
    yield


app = FastAPI(title="Stewarding Operations Management System", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
for module in (auth, employees, attendance, roster, checklists, uploads, equipment, temperature, inventory, stock,
               breakage, notifications, dashboard, reports, settings_api, audit):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
