#!/bin/sh
set -e

alembic upgrade head

# One worker: the in-process scheduler must run once. Duplicate generation is also blocked by database constraints.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers
