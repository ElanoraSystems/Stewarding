# Stewarding Operations Management System

Multi-location stewarding operations: attendance, daily and weekly checklists, dishwasher and glasswasher temperature
monitoring, crockery and smallware inventory, breakage, notifications, dashboards and reports. Three roles (Back of House
Manager, Stewarding Supervisor, Steward) are enforced on the server, including per-location access.

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - run it with Docker, create the first manager, back up, upgrade.
- [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) - rules that need management sign-off, assumptions, known limits.
- [docs/PLAN.md](docs/PLAN.md) - architecture and phases.

## Run with Docker
```bash
cp .env.example .env     # set POSTGRES_PASSWORD and STW_SECRET_KEY
docker compose up -d --build
docker compose run --rm backend python -m app.bootstrap --email you@company.com --name "Your Name" --code E001
```
Open http://localhost:8080. See the deployment guide for details.

## Where things are configured
Managers open **Settings**: locations, shifts, monitoring schedules (stages, timing and temperature limits per machine),
item master, categories and units, suppliers, alert rules and dropdown lists. Deliveries and supplier invoices are posted
under **Stock Movements, Receiving & invoices** and update stock through the ledger.

## Develop locally
Backend (Python 3.11):
```bash
cd backend
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env            # set STW_SECRET_KEY (32+ characters)
.venv/bin/alembic upgrade head
STW_SEED_PASSWORD=choose-one .venv/bin/python -m app.seed      # demo users and data
.venv/bin/uvicorn app.main:app --reload --port 8100
```
Frontend (Node 20):
```bash
cd frontend
npm install
npm run dev            # proxies /api to http://localhost:8100; override with VITE_API_TARGET
```
If the app shows "Cannot reach the server", the API is not running on that port.

## Tests
```bash
cd backend && .venv/bin/python -m pytest                       # SQLite
STW_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db .venv/bin/python -m pytest   # PostgreSQL (disposable DB)
cd frontend && npm run lint && npm run build
```
The suite covers permissions on every route, cross-location isolation, attendance and time zones, daylight saving,
checklist generation, temperature failures and retests, inventory ledger integrity, breakage approval, alerts, reports
and exports.

## Dependencies worth knowing
`openpyxl` and `reportlab` write the Excel and PDF exports (nothing else installed does); `psycopg` is the PostgreSQL driver.
