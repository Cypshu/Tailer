# TAILER Backend

FastAPI backend for the TAILER development prototype.

## Current behavior

- JWT login for mock users at `POST /api/auth/login`
- JWT-protected admin and user routes
- Sub-API-key-protected `POST /v1/chat/completions`
- validated request boundaries, active/expiry checks, and allowed-model checks
- `MockProvider` response
- measured latency and successful usage appended to in-memory state
- SQLAlchemy and Alembic scaffolding that active routes do not use

Development security limitations:

- passwords are display names;
- raw Sub-API keys are stored and returned;
- quotas, budgets, and per-key max-token policy are not enforced;
- only successful runtime calls create usage events;
- no upstream provider is called.

## Run locally

~~~bash
python -m venv venv
# Activate venv
pip install -r requirements.txt
python main.py
~~~

- Backend: http://localhost:8000
- Health: http://localhost:8000/health
- OpenAPI: http://localhost:8000/docs

Run commands from the `backend` directory so imports and local environment behavior match the application entrypoint.

## Modules

~~~text
app/
  api/
    auth.py       login and refresh placeholder
    admin.py      admin users, keys, usage, dashboard
    user.py       authenticated self-service routes
    runtime.py    OpenAI-style runtime route
  auth.py         JWT and password helpers
  config.py       TAILER-prefixed settings
  database.py     inactive SQLAlchemy engine/session scaffold
  main.py         app, CORS, routers, health
  mock_data.py    active mutable development state
  models.py       active Pydantic API schemas
  models_db.py    inactive SQLAlchemy schemas
  providers.py    provider protocol and MockProvider
alembic/
  versions/0001_initial_schema.py
tests/            isolated API and migration regression suite
alembic.ini
main.py
requirements-dev.txt
requirements.txt
~~~

## API route families

| Credential | Routes |
| --- | --- |
| None | `GET /`, `GET /health`, `POST /api/auth/login` |
| Dashboard JWT | `/admin/*` and `/user/*` |
| TAILER Sub-API key | `POST /v1/chat/completions` |

A dashboard JWT and a runtime Sub-API key are different credentials.

## Demo identities

| ID | Email | Password | Role |
| --- | --- | --- | --- |
| `user_3` | `organizer@hackathon.dev` | `Hackathon Organizer` | admin |
| `user_1` | `team_alpha@hackathon.dev` | `Team Alpha` | user |
| `user_2` | `team_beta@hackathon.dev` | `Team Beta` | user |

## Configuration

`app/config.py` declares these TAILER settings:

- `TAILER_APP_NAME`
- `TAILER_DEBUG`
- `TAILER_BACKEND_URL`
- `TAILER_FRONTEND_URL`
- `TAILER_DATABASE_URL`
- `TAILER_REDIS_URL`
- `TAILER_SECRET_KEY`
- `TAILER_JWT_SECRET_KEY`
- `TAILER_JWT_ALGORITHM`
- `TAILER_JWT_EXPIRATION_MINUTES`

Dashboard token encoding and decoding use `TAILER_JWT_SECRET_KEY`, `TAILER_JWT_ALGORITHM`, and `TAILER_JWT_EXPIRATION_MINUTES`. `TAILER_SECRET_KEY` remains reserved for other application signing or encryption work.

## Persistence

`database.py`, `models_db.py`, and the initial migration are scaffolding only. Active routes import `MOCK_USERS`, `MOCK_KEYS`, and `MOCK_USAGE_EVENTS` directly.

Alembic resolves its connection from `TAILER_DATABASE_URL`. Offline SQL generation and a disposable SQLite upgrade/downgrade/re-upgrade are verified; a PostgreSQL round-trip remains unverified while Docker is unavailable.

## Tests

Install test dependencies and run the isolated regression suite from this directory:

~~~bash
pip install -r requirements-dev.txt
python -m pytest
~~~

The suite uses FastAPI `TestClient`, restores mutable mock/provider state around each test, and does not need a live backend, PostgreSQL, or Redis process.

## Verified checks

~~~bash
python -m compileall -q app
python -m pytest
alembic heads
alembic upgrade head --sql
~~~

See [testing](../docs/testing.md) for the dated verification record.
