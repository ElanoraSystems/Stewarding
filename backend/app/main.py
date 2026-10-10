from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth
from .config import settings

app = FastAPI(title="Stewarding Operations Management System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
