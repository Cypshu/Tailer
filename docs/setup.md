# TAILER Setup Guide

TAILER runs as a durable PostgreSQL-backed development prototype. The seeded
development path uses a deterministic mock fallback; operators can create an
encrypted credential and model alias for the OpenAI Chat Completions or native
Gemini Interactions adapter.
Redis is present for future policy counters but is not consumed by active
request code.

## Prerequisites

Choose one path:

- Docker Desktop or another Docker Engine with Compose v2, or
- Python 3.12, Node.js 20, and PostgreSQL 16 for direct host development

## Docker Compose

The root lifecycle controllers are the simplest way to operate the stack. They resolve the repository directory themselves, create `.env` from `.env.example` if missing, and wait for all services to become healthy.

### Windows controller

Double-click `tailer.cmd` to open its interactive menu, or use command mode from Command Prompt or PowerShell:

~~~powershell
.\tailer.cmd start
.\tailer.cmd status
.\tailer.cmd logs backend frontend
.\tailer.cmd restart
.\tailer.cmd stop
.\tailer.cmd gemini-smoke  # explicit external/paid verification only
~~~

### Bash controller

~~~bash
chmod +x tailer.sh
./tailer.sh start
./tailer.sh status
./tailer.sh logs backend frontend
./tailer.sh restart
./tailer.sh stop
./tailer.sh gemini-smoke   # explicit external/paid verification only
~~~

Both controllers support:

| Command | Behavior |
| --- | --- |
| `start` | Build, start detached, wait for health, and print status |
| `stop` | Stop the stack and remove its containers/network; named data volumes remain |
| `restart` | Stop, rebuild, start, and wait for health |
| `status` | Show Compose service status |
| `logs [service...]` | Follow recent logs, optionally for selected services |
| `config` | Validate the rendered Compose configuration |
| `gemini-smoke` | Run the loopback-only disposable Gemini pipeline; never part of startup |
| `help` | Show command help |

`TAILER_COMPOSE_WAIT_TIMEOUT` controls the health wait in seconds (default `300`), and `TAILER_COMPOSE_LOG_TAIL` controls initial log lines (default `200`).

Direct Compose remains equivalent:

~~~bash
cp .env.example .env
docker compose up --build --detach --wait
~~~

On PowerShell, use `Copy-Item .env.example .env`.

After startup:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Liveness: http://localhost:8000/health
- Persistence readiness: http://localhost:8000/ready
- API schema: http://localhost:8000/docs

PostgreSQL and Redis become healthy before the backend starts, and the frontend waits for backend readiness. The backend container runs `alembic upgrade head` and the idempotent demo seed before FastAPI starts. `/health` checks process liveness without downstream I/O; `/ready` queries the configured repository and returns 503 if persistence is unavailable.

### Environment warning

The examples contain development defaults. Before any shared deployment,
replace at least the PostgreSQL password, `TAILER_JWT_SECRET_KEY`,
`TAILER_SECRET_KEY`, and `TAILER_SUB_API_KEY_PEPPER`, and configure an
operator-owned provider-credential encryption keyring. Do not add real provider
credentials or encryption keys to source control. Changing the Sub-API-key
pepper makes every existing bearer key unusable.

`TAILER_DEBUG` defaults to `false`, which also keeps SQL statement parameters out
of normal backend logs. Enable it only for a short local diagnostic and do not
collect debug SQL logs from workloads containing sensitive identity data.

### Provider-credential encryption

Generate a URL-safe base64 AES-256 key from `backend/`:

~~~bash
python -c "from app.credential_security import generate_credential_encryption_key as g; print(g())"
~~~

Store the generated output in a secret manager or local untracked `.env`:

~~~dotenv
TAILER_CREDENTIAL_ENCRYPTION_KEYS={"v1":"<generated URL-safe base64 AES-256 key>"}
TAILER_CREDENTIAL_ACTIVE_KEY_VERSION=v1
TAILER_OPENAI_BASE_URL=https://api.openai.com/v1
TAILER_GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1
TAILER_PROVIDER_TIMEOUT_SECONDS=30
~~~

`TAILER_CREDENTIAL_ENCRYPTION_KEYS` is a JSON mapping. New credentials use the
active version; keep every older version needed by existing rows during key
rotation. AES-256-GCM associated data binds each ciphertext to its credential
ID, project ID, provider, and key version. Credential creation and real-provider
resolution fail closed if the registry is empty, malformed, missing the active
version, or unable to authenticate a stored value. An empty registry is suitable
only for the mock path.

Do not put an upstream provider API key itself in a Compose file or checked-in
environment file. Supply it once to `POST /admin/provider-credentials`; the API
returns only metadata and persistence stores authenticated ciphertext plus a
safe suffix hint. See the environment-only disposable credential flow in the
[testing guide](testing.md).

### Opt-in live Gemini pipeline

This verification mutates the local development database, makes model-discovery
plus two paid/external completion calls, restarts services, then removes its
exact rows and restores the canonical empty-keyring stack. It is loopback-only
and refuses transient Compose overrides or a database that already contains
provider credentials/model routes;
run it only while you have exclusive use of the development stack.

Put one disposable Gemini API key in the ignored root `.gemini_api` file. Use a
single raw line (or `GEMINI_API_KEY=<value>`), never print it, and on Unix restrict
the file before running:

~~~bash
chmod 600 .gemini_api
./tailer.sh gemini-smoke
~~~

On Windows, run `.\tailer.cmd gemini-smoke`. The key remains in the host runner,
is submitted once through the credential API, and is never placed in Docker
environment variables, build contexts, command arguments, or checked-in files.
Delete the file and rotate/revoke the disposable key after verification.

## Linux systemd service

[`deploy/systemd/tailer.service`](../deploy/systemd/tailer.service) manages the complete detached Compose stack as one boot service and delegates lifecycle operations to `tailer.sh`. Its checked-in paths assume the repository is installed or linked at `/opt/tailer`.

~~~bash
sudo ln -s /absolute/path/to/Tailer /opt/tailer
cd /opt/tailer
sudo cp .env.example .env
sudo chmod 600 .env
sudo chmod +x tailer.sh
sudo install -m 0644 deploy/systemd/tailer.service /etc/systemd/system/tailer.service
sudo systemctl daemon-reload
sudo systemctl enable --now tailer.service
~~~

Operate it with:

~~~bash
sudo systemctl status tailer.service
sudo systemctl restart tailer.service
sudo systemctl stop tailer.service
sudo journalctl -u tailer.service
~~~

The unit is `Type=oneshot` with `RemainAfterExit=yes`: systemd owns stack start/stop while Compose supervises the detached containers. Read the full [systemd guide](../deploy/systemd/README.md) before changing its path or using rootless Docker.

## Direct local development

### Backend with PostgreSQL

Start PostgreSQL 16 and ensure the host can reach it at the URL in `backend/.env`. Then:

~~~bash
cd backend
python -m venv venv
# Activate venv for your shell
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.bootstrap
python main.py
~~~

PowerShell activation and environment copy:

~~~powershell
.\venv\Scripts\Activate.ps1
Copy-Item .env.example .env
~~~

The backend runs at http://localhost:8000. Use `requirements-dev.txt` instead when developing or testing; it includes runtime requirements.

### Isolated in-memory adapter

The in-memory adapter is retained for tests and lightweight isolated development. Select it with `TAILER_REPOSITORY_BACKEND=memory`; it starts from deterministic demo records and does not require a database connection. Its mutations disappear when the backend process exits.

~~~powershell
$env:TAILER_REPOSITORY_BACKEND = "memory"
python main.py
~~~

~~~bash
TAILER_REPOSITORY_BACKEND=memory python main.py
~~~

Do not use this adapter when validating persistence or restart durability.

### Frontend

In another terminal:

~~~bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
~~~

On PowerShell, replace the copy command with `Copy-Item .env.example .env.local`. `NEXT_PUBLIC_API_URL` defaults to http://localhost:8000.

## Database and migrations

Two PostgreSQL hostnames serve different execution contexts:

- Containers use `postgres:5432`.
- Host tools use the published port at `localhost:5432`.

Alembic reads `TAILER_DATABASE_URL` through the same settings object as the application. From `backend/`, a disposable round-trip is:

~~~bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
python -m app.bootstrap
~~~

Only downgrade a disposable database because `base` removes application tables. The seed inserts the fixed development users, project, keys, and usage in foreign-key order. Re-running it is safe for compatible records; fixed-ID or normalized-email collisions abort rather than overwrite data. If the pepper changes, the seed deliberately leaves existing key digests untouched instead of silently rotating credentials.

Inside the backend container:

~~~bash
docker compose exec backend alembic current
docker compose exec backend python -m app.bootstrap
~~~

Offline SQL generation does not require a database:

~~~bash
cd backend
alembic upgrade head --sql
~~~

The automated migration suite reaches head `0003`, which adds
`provider_credentials` and `model_configs`. A clean disposable PostgreSQL 16
database also passed upgrade, `alembic check`, downgrade to base, and re-upgrade
at `0003`; the probe database was removed. The previous Iteration 1 checkpoint
verified the same durability shape at revision `0002`.

## Verification

~~~bash
# Frontend
cd frontend
npm run lint
npm run build

# Backend
cd ../backend
python -m compileall -q app tests
python -m pytest -q

# Repository root
cd ..
docker compose config --quiet
./tailer.sh config
~~~

On Windows, use `.\tailer.cmd config`. See [testing](testing.md) for the automated suite, dated results, and optional manual smoke flow.

The current backend verification is 229 passing tests in normal and reversed
file order. This includes mocked upstreams for the OpenAI and Gemini adapters.
A live configured encrypted route
to a deliberately non-routable HTTPS upstream verified sanitized
`provider_unavailable` handling, durable `error_code` persistence across backend
restart, and API/log redaction. A final `tailer.cmd restart` left all four
services healthy at `0003`, with a passing mock completion and an intentionally
empty keyring. The loopback-only Gemini pipeline then completed twice across
restart, verified durable priced usage and secret redaction, removed exact probe
rows, and restored all four services. Iteration 2 is complete.

## Common problems

### Port already in use

Check ports 3000, 5432, 6379, and 8000 before startup, or change the published ports consistently.

### Startup times out

Run `tailer.cmd status` or `./tailer.sh status`, then inspect with `tailer.cmd logs postgres backend frontend` or `./tailer.sh logs postgres backend frontend`. Increase `TAILER_COMPOSE_WAIT_TIMEOUT` for a slow first build.

### Frontend cannot reach the backend

Confirm:

- the backend liveness and readiness URLs respond;
- `NEXT_PUBLIC_API_URL` points to the browser-accessible backend;
- the frontend origin matches backend CORS configuration.

### Login fails

Use the exact development fixtures:

- `organizer@hackathon.dev` / `Hackathon Organizer`
- `team_alpha@hackathon.dev` / `Team Alpha`
- `team_beta@hackathon.dev` / `Team Beta`

Passwords are case-sensitive display names in the current prototype.

### Expected data is missing

Confirm `TAILER_REPOSITORY_BACKEND=sqlalchemy`, inspect backend startup logs for migration/seed failures, and check the configured database URL. Normal `tailer.cmd stop` or `./tailer.sh stop` preserves the PostgreSQL named volume; removing that volume deletes durable development data.

### A configured model returns 503

Confirm the alias is enabled, its credential is active, and the credential row
matches the same project and provider. Also confirm the row's `key_version`
exists in `TAILER_CREDENTIAL_ENCRYPTION_KEYS`. TAILER deliberately returns a
sanitized configuration error instead of exposing decryption details.
