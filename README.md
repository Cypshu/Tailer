# TAILER

TAILER is a prototype LLM access gateway. It gives dashboard users managed Sub-API keys, exposes an OpenAI-style chat endpoint, and records demo usage without sharing an upstream provider credential.

> Current maturity: demonstrable mock-backed prototype, not a secure or production-ready gateway.

## What works

- Next.js 16 admin, user, login, and landing pages
- FastAPI auth, admin, user, health, and runtime routes
- JWT-based dashboard login and role checks
- Validated API boundaries and configured JWT signing/lifetime
- Sub-API-key authentication, expiration, and per-key model allow-list checks
- Mock provider responses, measured latency, and in-memory usage recording
- Isolated FastAPI regression tests
- SQLAlchemy models and an initial Alembic migration scaffold
- Docker Compose definitions for PostgreSQL, Redis, backend, and frontend

## Important limitations

- Active routes use mutable in-memory data; restarts discard changes.
- Demo passwords are user display names.
- Raw Sub-API keys are stored and returned by read APIs.
- PostgreSQL, Redis, and the Alembic scaffold are not wired into active routes.
- There is no real provider adapter, provider credential vault, or durable audit log.
- Request-count, token, and budget quotas are not enforced yet.

Do not use the current prototype with real credentials or untrusted clients.

## Quick start

### Docker Compose

~~~bash
cp .env.example .env
docker compose up --build
~~~

Open:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API schema: http://localhost:8000/docs
- Health: http://localhost:8000/health

The convenience scripts `start.cmd` and `start.sh` perform the same Compose startup.

### Local development

~~~bash
# Terminal 1
cd backend
python -m venv venv
# Activate venv for your shell
pip install -r requirements-dev.txt
python main.py

# Terminal 2
cd frontend
npm install
npm run dev
~~~

See [setup](docs/setup.md) for environment and migration notes.

## Demo identities

| Role | Email | Demo password |
| --- | --- | --- |
| Admin | `organizer@hackathon.dev` | `Hackathon Organizer` |
| User | `team_alpha@hackathon.dev` | `Team Alpha` |
| User | `team_beta@hackathon.dev` | `Team Beta` |

These credentials are intentionally insecure fixtures.

## Documentation map

- [Agent guide](AGENTS.md): repository rules and handoff entrypoint
- [Active task board](tasks.md): the next executable work
- [Implementation plan](TAILER_Project_Implementation_Plan.md): ordered delivery slices and acceptance gates
- [Product charter](docs/product.md): product scope and invariants
- [Architecture](docs/architecture.md): current and target technical shape
- [Setup guide](docs/setup.md): local and Compose startup
- [Testing guide](docs/testing.md): verified checks and manual smoke flow
- [Archive](docs/archive/README.md): historical snapshots that are not current sources of truth

## Verified baseline

On 2026-08-02:

- `npm run lint` passed.
- `npm run build` passed.
- A live local backend smoke test passed for login, RBAC, user identity, valid runtime access, and invalid-key rejection.
- The isolated backend regression suite passed without live services.
- `docker compose config --quiet` passed.
- `alembic upgrade head --sql` passed.
- A disposable SQLite database passed upgrade/downgrade/re-upgrade and schema-drift checks.
- A PostgreSQL migration round-trip and full Compose startup were not verified because the Docker daemon was unavailable.

The next implementation slice is the persistence mapping and repository boundary described in the [implementation plan](TAILER_Project_Implementation_Plan.md). Docker-backed verification remains an explicit prerequisite for the durable cutover.
