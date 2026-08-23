# TAILER

TAILER is a development-stage LLM access gateway. It gives dashboard users managed Sub-API keys, exposes an OpenAI-style chat endpoint, and records durable usage without sharing an upstream provider credential.

> Current maturity: secure-provider development prototype. The repository
> contains mocked-provider coverage and an explicit, opt-in live-provider smoke
> path. Never place provider credentials in Git.

## What works

- Next.js 16 admin, user, login, and landing pages
- FastAPI auth, admin, user, health, and runtime routes
- JWT-based dashboard login and role checks
- Validated API boundaries and configured JWT signing/lifetime
- SQLAlchemy repositories backed by PostgreSQL by default
- An in-memory repository adapter retained for isolated tests
- Alembic migrations and an idempotent deterministic development seed
- Newly created random Sub-API keys stored as peppered HMAC-SHA-256 digests
- Creation-only raw-key reveal; later reads expose a safe display prefix
- Active, expiration, project, and per-key model allow-list checks
- Versioned AES-256-GCM encryption for upstream credentials, bound to credential,
  project, provider, and key version through authenticated associated data
- Metadata-only admin APIs for provider credentials and model configurations
- Public-model alias routing to OpenAI Chat Completions or native Gemini
  Interactions, with per-million-token EUR pricing supplied by the model
  configuration
- Deterministic mock-provider fallback for the unconfigured development seed
- Measured latency plus durable success and sanitized provider-failure usage events
- A 229-case regression suite, including mocked-upstream OpenAI and Gemini
  integration tests, that runs API contracts against both repository adapters
- Docker Compose health checks and dependency sequencing for PostgreSQL, Redis, backend, and frontend

## Important limitations

- Demo passwords are user display names, and the checked-in configuration values are development defaults.
- Deterministic demo bearer keys exist in source for repeatable testing. Do not use them outside development.
- Live success is verified with Gemini 3.6 Flash. OpenAI-specific live success
  remains unverified, but it is no longer the provider-neutral iteration gate.
- Provider credential and model management are backend APIs only; the frontend
  has no management screen for them.
- Redis is started by Compose but request-rate, token, budget, and per-key maximum-token limits are not enforced.
- Provider failures create durable sanitized events, but pre-provider blocked
  requests are not yet written as audit events.
- Credential re-encryption primitives exist, but an operator rotation workflow,
  secure user-password management, HTTPS, backups, and production secret
  management remain outstanding.

Do not use the current prototype with long-lived or production credentials or
with untrusted clients. Use only a disposable provider credential for the
documented opt-in live smoke.

## Quick start

Docker Desktop or another Docker Engine with Compose v2 is the recommended path.

### Windows

Double-click `tailer.cmd` for an interactive menu, or run:

~~~powershell
.\tailer.cmd start
.\tailer.cmd status
.\tailer.cmd logs
~~~

### Linux and macOS

~~~bash
chmod +x tailer.sh
./tailer.sh start
./tailer.sh status
./tailer.sh logs
~~~

Both controllers support `start`, `stop`, `restart`, `status`, `logs`, `config`,
`gemini-smoke`, and `help`. They create `.env` from `.env.example` when needed,
build the stack, and wait for service health. `gemini-smoke` is an explicit,
external paid test and is never part of normal startup. Direct `docker compose`
commands remain available.

Open:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API schema: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Persistence readiness: http://localhost:8000/ready

The backend container applies Alembic migrations and runs the idempotent demo seed before starting FastAPI. See the [setup guide](docs/setup.md) for direct host development and [systemd guide](deploy/systemd/README.md) for a Linux boot service.

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
- [Setup guide](docs/setup.md): lifecycle commands, local startup, Compose, and systemd
- [Testing guide](docs/testing.md): verified checks and manual smoke flow
- Private architecture, product decisions, task state, and historical material
  live only in the ignored local `arch/` directory.

## Verified baseline

Verified through 2026-08-02:

- Frontend lint and production build passed.
- The Iteration 2 backend suite passed all 229 tests in normal and reversed file
  order, including encryption, metadata redaction, OpenAI/Gemini routing,
  adapter contracts, orchestration safety, normalized errors, and durable usage.
- Every API characterization runs against a fresh in-memory store and a fresh Alembic-migrated SQLite database.
- The automated migration suite reaches Alembic head `0003`, which adds
  `provider_credentials` and `model_configs`.
- The previous Iteration 1 baseline passed all 121 tests in normal and reversed
  file order; revision `0002` also passed its SQLite checks and a clean
  PostgreSQL 16 round-trip.
- A clean backend image built with `cryptography` 49.0.0, and a disposable
  PostgreSQL 16 database passed upgrade/check/downgrade/re-upgrade at `0003`.
- Docker Engine 29.6.1 and Compose 5.2.0 built and started all four services healthy.
- Backend/frontend HTTP checks and an admin login passed through the Compose stack.
- Lifecycle script configuration checks and Unix shell syntax checks passed.
- A live controller restart preserved a created user, revoked key, and usage
  event; concurrent duplicate creation returned 200/409 and probe data was
  removed afterward.
- A live encrypted-credential/model route against a deliberately non-routable
  HTTPS upstream produced sanitized `provider_unavailable`, persisted its
  `error_code` across backend restart, and exposed no plaintext/ciphertext in
  APIs or logs. Its exact rows were removed.
- A final `tailer.cmd restart` left all four services healthy at database head
  `0003`; the deterministic mock completion passed and the container was
  intentionally returned to an empty credential keyring.
- Live-provider smoke tests are optional development checks and require a
  disposable credential supplied only through an ignored local file.

Consult the [task board](tasks.md) for the next implementation slice and remaining risks.
