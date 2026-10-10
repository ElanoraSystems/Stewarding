# Stewarding Operations Management System

Multi-location stewarding operations: attendance, checklists, dishwasher/glasswasher temperature
monitoring, crockery and smallware inventory, breakage, notifications and reports.

See [docs/PLAN.md](docs/PLAN.md) for architecture, phases and items needing management approval.

## Backend

```bash
cd backend
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env            # then set STW_SECRET_KEY
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload
.venv/bin/python -m pytest
```

Seeded users (all `@example.test`): `manager`, `sup.mk`, `sup.rb`, `steward.mk`, `steward.bq`, `steward.rb`.
The password is `STW_SEED_PASSWORD`, or the random value the seed command prints.

## Frontend

```bash
cd frontend
npm install
npm run dev
```
