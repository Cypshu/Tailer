# TAILER Setup Guide

TAILER currently runs as a mock-backed development prototype. PostgreSQL and Redis are defined for upcoming work but are not used by active routes.

## Prerequisites

Choose one path:

- Docker Desktop or another Docker Engine with Compose v2, or
- Python 3.12 and Node.js 20 for direct local development

## Docker Compose

From the repository root:

~~~bash
cp .env.example .env
docker compose up --build
~~~

On PowerShell, use:

~~~powershell
Copy-Item .env.example .env
docker compose up --build
~~~

Convenience wrappers are also available:

- Windows: `start.cmd`, `restart.cmd`, `stop.cmd`
- Bash: `./start.sh`, `./restart.sh`, `./stop.sh`

After startup:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Health: http://localhost:8000/health
- API schema: http://localhost:8000/docs

Use `docker compose ps` and `docker compose logs backend frontend` to inspect startup. PostgreSQL and Redis are checked before the backend starts, and the frontend waits for the backend health check. All four services define health checks.

### Environment warning

The example contains development defaults. Replace `TAILER_SECRET_KEY` and `TAILER_JWT_SECRET_KEY` before using a shared environment. Do not add real provider credentials to source control.

## Direct local development

### Backend

~~~bash
cd backend
python -m venv venv
~~~

Activate the virtual environment:

~~~powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
~~~

~~~bash
# Bash
source venv/bin/activate
~~~

Install and start the app only:

~~~bash
pip install -r requirements.txt
python main.py
~~~

For backend development and tests, use the development requirements instead; they include the runtime requirements:

~~~bash
pip install -r requirements-dev.txt
~~~

The backend runs at http://localhost:8000.

The current app does not connect to PostgreSQL during route startup, so the mock-backed API can run without the database service.

### Frontend

In another terminal:

~~~bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
~~~

On PowerShell, replace the copy command with:

~~~powershell
Copy-Item .env.example .env.local
~~~

`NEXT_PUBLIC_API_URL` defaults to http://localhost:8000.

## Database and migrations

Two hostnames serve different execution contexts:

- Containers reach PostgreSQL at `postgres:5432`.
- Host tools reach the published port at `localhost:5432`.

Alembic reads `TAILER_DATABASE_URL` through the same settings object as the application. The default in `backend/.env.example` targets the host-published PostgreSQL port. From `backend/`:

~~~powershell
Copy-Item .env.example .env
alembic upgrade head
alembic downgrade base
alembic upgrade head
~~~

The equivalent Bash setup is `cp .env.example .env`. Only run the downgrade against a disposable development database because it drops the scaffold tables.

Inside the running backend container, the root Compose environment uses the `postgres` service hostname:

~~~bash
docker compose exec backend alembic upgrade head
~~~

Offline SQL generation does not require a database:

~~~bash
cd backend
alembic upgrade head --sql
~~~

The SQLite round-trip is automated; PostgreSQL upgrade/downgrade remains an explicit Docker-backed verification task. Do not claim the PostgreSQL schema is applied merely because the migration files exist.

## Verification

~~~bash
# Frontend
cd frontend
npm run lint
npm run build

# Backend syntax
cd ../backend
python -m compileall -q app
python -m pytest

# From repository root
cd ..
docker compose config --quiet
~~~

See [testing](testing.md) for the automated suite, dated results, and optional manual smoke flow.

## Common problems

### Port already in use

Check ports 3000, 5432, 6379, and 8000 before startup, or change the published ports consistently.

### Frontend cannot reach the backend

Confirm:

- the backend health URL responds;
- `NEXT_PUBLIC_API_URL` points to the browser-accessible backend;
- the frontend origin matches backend CORS configuration.

### Login fails

Use the exact development fixtures:

- `organizer@hackathon.dev` / `Hackathon Organizer`
- `team_alpha@hackathon.dev` / `Team Alpha`
- `team_beta@hackathon.dev` / `Team Beta`

Passwords are case-sensitive display names in the current prototype.

### State disappears

This is expected. Active routes mutate in-memory lists and reset when the backend process restarts.
