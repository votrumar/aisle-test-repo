# Storage Conditions Monitoring

FastAPI service for ingesting sensor measurements (temperature, humidity, …),
evaluating threshold alerts on write, and viewing recent data in a built-in
Jinja2 + Chart.js dashboard. Backed by Postgres. Dashboard and read APIs are
public, while `POST /measurements` requires a sensor-scoped bearer token.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2.x + `psycopg` driver
- Postgres 16 (schema bootstrapped from `scripts/init.sql`)
- Jinja2 templates + Chart.js (loaded from CDN) for the dashboard
- Docker Compose for local orchestration

## Layout

```
src/monitoring/
  main.py            FastAPI app factory + router mounting
  config.py          DATABASE_URL via pydantic-settings
  db.py              SQLAlchemy engine + session dependency
  models.py          ORM models
  schemas.py         Pydantic request/response models
  alerts.py          Synchronous threshold evaluation
  routers/           JSON + dashboard routes
  templates/         Jinja2 HTML
  static/app.js      Chart.js wiring
scripts/init.sql     CREATE TABLE statements (mounted into the Postgres container)
tests/test_api.py    End-to-end pytest suite
Dockerfile
docker-compose.yml
```

## Run locally (Docker Compose)

```bash
docker compose up --build
```

- API: <http://localhost:8000>
- Dashboard: <http://localhost:8000/>
- OpenAPI docs: <http://localhost:8000/docs>
- Postgres: `localhost:5432` (user/pass/db: `monitoring`)

The Postgres container runs `scripts/init.sql` on first start (it is mounted
read-only into `/docker-entrypoint-initdb.d/`). Drop the `pgdata` volume
(`docker compose down -v`) if you want to re-seed the schema.

## Run locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Point at a running Postgres and apply the schema once:
psql "$DATABASE_URL" -f scripts/init.sql
export DATABASE_URL=postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring
uvicorn monitoring.main:app --reload
```

## API quick tour

```bash
# Create a sensor
curl -X POST http://localhost:8000/sensors \
  -H 'content-type: application/json' \
  -d '{"name":"freezer-1","location":"warehouse-A"}'

# Create an alert rule (fire when temperature > -15 C)
curl -X POST http://localhost:8000/alert-rules \
  -H 'content-type: application/json' \
  -d '{"name":"too-hot","sensor_id":1,"metric":"temperature","comparator":"gt","threshold":-15}'

# Submit a measurement (will trigger the rule)
# DEVICE_TOKEN must be signed with JWT_SECRET and scoped to sensor 1
curl -X POST http://localhost:8000/measurements \
  -H 'content-type: application/json' \
  -H "Authorization: Bearer $DEVICE_TOKEN" \
  -d '{"sensor_id":1,"metric":"temperature","value":-10,"unit":"C"}'

# Inspect triggered alerts
curl http://localhost:8000/alert-events
```

Alert evaluation runs **synchronously** inside the same DB transaction as the
measurement insert. The `POST /measurements` response includes a
`triggered_alerts` array so clients can react inline. Triggered events are
also persisted in `alert_events` and surfaced on the dashboard.

## Dashboard

- `/` — list of sensors and the most recent alert events.
- `/sensors/{id}/view` — Chart.js line chart of the sensor's measurements
  (defaults to the last 24 hours), grouped by metric, plus the sensor's recent
  alert events.

## Tests

```bash
pip install -r requirements.txt
# Tests need a Postgres pointed at by DATABASE_URL with the schema applied.
export DATABASE_URL=postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring
psql "$DATABASE_URL" -f scripts/init.sql   # idempotent if already applied
pytest
```

Or, against the docker-compose stack:

```bash
docker compose up -d db
DATABASE_URL=postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring pytest
```
