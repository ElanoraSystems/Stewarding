# Stewarding Operations Management System - Plan

## Discovery
The repository started empty. No existing framework, dependencies, database, or authentication.

## Architecture
- `backend/` FastAPI + SQLAlchemy 2 + Alembic. SQLite in development, PostgreSQL in production via `DATABASE_URL`.
- `frontend/` Vite + React + TypeScript + Tailwind + shadcn-style components + Lucide icons.
- Auth: bcrypt password hashes, signed JWT access token. Every protected endpoint declares its permission server-side.
- Authorization: role -> permission set, plus location scoping. Managers see all locations; supervisors and stewards see only locations they are assigned to.
- Time: all timestamps stored as UTC and generated on the server. Each location has an IANA timezone; "today" and deadlines are computed in that timezone.
- Immutability: stock transactions, temperature readings, and attendance rows are append-only. Corrections are new rows (adjustment, retest, correction record) plus an audit entry.
- Scheduler: an in-process job generates checklist instances idempotently (unique on task + location + local date + shift) and emits de-duplicated notifications.

## Configuration, not hardcoding
Temperature limits and frequencies (per equipment), late grace minutes, overtime thresholds, break rules, reminder lead times, escalation delays, breakage approval threshold, shift definitions, checklist content, inventory categories and units.

## Phases
1. Foundation: schema, migrations, auth, RBAC + location scoping, nav shell, seed data.
2. Workforce and tasks: employees, attendance, shifts, checklists.
3. Monitoring: points, configurable checks and frequencies, logs, corrective actions.
4. Inventory and incidents: one inventory (categories separate the items), transactions, transfers, counts, breakage.
5. Notifications and reporting: reminders, escalation, reports, exports, audit views.
6. Testing and release: test suites, build, Docker deployment docs.

## Items needing management approval
- Acceptable temperature limits per machine (seed values are placeholders to be set from manufacturer instructions and the organization's food-safety procedure).
- Machine display temperature vs. independent rinse/sanitizing verification: modelled as separate monitoring stages.
- Breakage approval threshold and overtime/break rules.
