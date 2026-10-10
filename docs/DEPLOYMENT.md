# Deployment

The application ships as three containers: PostgreSQL, the FastAPI backend, and nginx serving the built React app and proxying `/api`.

## Requirements
- Docker with Compose v2.
- A host or reverse proxy that terminates HTTPS in front of the `web` container. Tokens travel in the `Authorization` header, so use HTTPS in production.

## First start
```bash
cp .env.example .env
```
Edit `.env`:
- `POSTGRES_PASSWORD`: a long random password.
- `STW_SECRET_KEY`: 32 or more random characters. Generate one with
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The backend refuses to start without it.
- `STW_CORS_ORIGINS`: the public address of the site, for example `https://stewarding.example.com`.

```bash
docker compose up -d --build
```
The backend applies database migrations on every start.

## Create the first manager
Do not run the demo seed in production. It creates sample users and sample data.

```bash
docker compose run --rm -e STW_BOOTSTRAP_PASSWORD='choose-a-long-password' backend \
  python -m app.bootstrap --email you@company.com --name "Your Name" --code E001
```
Or leave out `STW_BOOTSTRAP_PASSWORD` and use `docker compose run --rm backend ...` interactively to be prompted. This also creates the default dropdown lists (job titles, checklist categories, breakage reasons, standard corrective actions).

## First-time setup (Settings, in this order)
Sign in as the manager and open **Settings**. Each tab manages one kind of data:

1. **Locations** - kitchens, bars, banquet areas; time zone and optional check-in PIN.
2. **Shifts** - hours, late-after minutes, break and overtime rules.
3. **Categories & units** - item categories, units of measure.
4. **Suppliers** - the companies you receive stock from.
5. **Item master** - every item once (names are checked for duplicates and the item ID is generated automatically), linked to a category, unit and supplier.
6. **Monitoring schedules** - for each dishwasher and glasswasher: its stages, when each is checked, and the temperature limits. Limits are not pre-filled in production; set them from the manufacturer's instructions and your food-safety procedure.
7. **Rules & alerts** - reminder, escalation, retest and approval thresholds.
8. **Dropdown lists** - job titles, checklist categories, breakage reasons and standard corrective actions.

Then add employees and checklist templates (Daily Checklists, Configure) and receive opening stock under **Stock Movements, Receiving**.

## Demo data (non-production only)
```bash
docker compose exec -e STW_SEED_PASSWORD='demo-password-1' backend python -m app.seed
```
Seeded users are `manager`, `sup.mk`, `sup.rb`, `steward.mk`, `steward.bq` and `steward.rb` at `@example.test`. The seeded temperature limits are placeholders.

## Operations
- **Backups:** back up the `dbdata` volume (for example `pg_dump`) and the `uploads` volume (evidence photos).
- **Upgrades:** `git pull && docker compose up -d --build`. Migrations run automatically.
- **Scheduler:** it runs inside the backend process. Keep one backend replica and one worker. If you scale out, database constraints still prevent duplicate tasks and notifications, but alert jobs would run more than once.
- **Login lockout:** the failed-attempt counter is held in memory, so it is per process and resets on restart.
- **Time zones:** each location has an IANA time zone (Settings). All timestamps are stored in UTC and shown in the location's zone.
- **Logs:** `docker compose logs -f backend`.

## Development without Docker
See the README. Tests run on SQLite by default. To run them against PostgreSQL set
`STW_TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname` before `pytest`; the tests drop and recreate every table in that database, so point it at a disposable one.

## Verification performed
The compose stack was built and run end to end: migration, API through nginx, SPA fallback, security headers on every route type, seeding and sign-in. The full test suite passes on both SQLite and PostgreSQL 16, and `alembic check` reports no drift on PostgreSQL.
