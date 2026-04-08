# Portal Console

`portal-console` is a lightweight personal project portal for aggregating entry links, health status, and controlled start/stop/restart actions across servers and LAN devices.

## What is implemented

- FastAPI backend with JWT login, `admin` / `viewer` roles, SQLAlchemy models, and bootstrap admin creation
- Project, server, link, status sync, operation log, and action endpoints based on the design document
- Rundeck action adapter that triggers jobs by Job ID and records the Rundeck execution ID
- Conservative Uptime Kuma adapter that falls back to `unknown` when the instance does not expose a compatible endpoint
- Vue 3 + Element Plus frontend with login, dashboard, project detail, servers, logs, and settings views
- Docker Compose setup for `postgres`, `backend`, and `frontend`

## Structure

```text
portal-console/
  backend/   FastAPI service
  frontend/  Vue 3 console
  .env.example
  docker-compose.yml
```

## Quick start

1. Copy `.env.example` to `.env` and set `SECRET_KEY`, `RUNDECK_*`, and `KUMA_*` as needed.
2. Run `docker compose up --build` from `portal-console/`.
3. Open `http://localhost:8080`.
4. Sign in with `FIRST_SUPERUSER` / `FIRST_SUPERUSER_PASSWORD`.

Backend API will be available at `http://localhost:8000`, and interactive docs at `http://localhost:8000/docs`.

## Local validation stack

For a self-contained local demo without external Rundeck or Uptime Kuma instances:

1. Run `docker compose -f docker-compose.yml -f docker-compose.mock.yml up --build -d`.
2. Seed demo data:
   `env PYTHONPATH=/root/portal-console/backend DATABASE_URL=postgresql+psycopg://portal:portal@127.0.0.1:5432/portal_console SECRET_KEY=change-this-secret RUNDECK_URL=http://127.0.0.1:9000 RUNDECK_TOKEN=mock-token KUMA_URL=http://127.0.0.1:9000 KUMA_TOKEN= /root/portal-console/backend/.venv/bin/python /root/portal-console/scripts/seed_demo_data.py`
3. Open `http://localhost:8080` and sign in with `admin` / `admin123`.

The mock override exposes deterministic project states and successful Rundeck-like action responses so the dashboard, project detail, logs, and settings views can be exercised end-to-end.

## Notes

- The backend currently bootstraps tables with `SQLAlchemy` `create_all()` on startup for a fast MVP. `alembic` is already included in dependencies and a scaffold is provided under `backend/alembic/` so migrations can be added next.
- Rundeck integration is wired to the official job run and execution endpoints.
- Uptime Kuma does not have a stable public management API for monitor state, so the adapter in `backend/app/services/kuma.py` intentionally degrades to `unknown` if the configured instance does not match the expected shape.
