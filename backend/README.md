# TAILER Backend

FastAPI backend for the TAILER development prototype.

## Current behavior

- JWT login at `POST /api/auth/login`
- JWT-protected admin and user routes
- Sub-API-key-protected `POST /v1/chat/completions`
- Validated request boundaries and active, expiry, project, allowed-model, and
  optional per-key output-token ceiling checks
- Repository and unit-of-work boundaries shared by all active routes
- SQLAlchemy/PostgreSQL as the default runtime adapter
- An in-memory adapter for isolated tests
- Alembic migrations plus an idempotent deterministic demo seed
- Newly created random Sub-API keys stored only as peppered HMAC-SHA-256 digests
- Raw key returned once by `POST /admin/keys`; subsequent reads return `key_prefix`
- Versioned AES-256-GCM encryption for provider credentials, with authenticated
  associated data binding each ciphertext to its credential ID, project,
  provider, and key version
- Metadata-only provider-credential and model-configuration admin APIs
- Project-scoped public-model aliases that resolve a provider model, encrypted
  credential, and configured per-million-token EUR prices
- OpenAI Chat Completions and native Gemini Interactions adapters with sanitized
  timeout, connection, authentication, permission, not-found, rate-limit,
  rejection, and malformed-response failures
- Measured latency and durable success/provider-failure usage events, including
  a stable `error_code` for failures
- Deterministic `MockProvider` fallback when the development seed has no model route

Development limitations:

- passwords are seeded display names;
- deterministic demo bearer keys and development secrets exist in source;
- request-rate quotas and aggregate token/cost budgets are not enforced;
- pre-provider blocked requests do not yet create audit events;
- Redis is not used by active policy code;
- provider/model management has no frontend;
- both provider implementations have passed mocked-upstream integration tests;
  Gemini also passed the disposable live pipeline before and after restart.
  OpenAI-specific live success remains optional additional coverage.

## Run locally

Run commands from the `backend` directory. A direct host run uses PostgreSQL by default:

~~~bash
python -m venv venv
# Activate venv
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
python -m app.bootstrap
python main.py
~~~

On PowerShell, copy the environment with `Copy-Item .env.example .env`. PostgreSQL must be reachable through `TAILER_DATABASE_URL`; the example targets `localhost:5432`.

The migration and seed steps are automatic in the backend Docker image. The seed is idempotent and does not overwrite compatible operator changes.

- Backend: http://localhost:8000
- Liveness: http://localhost:8000/health
- Persistence readiness: http://localhost:8000/ready
- OpenAPI: http://localhost:8000/docs

`TAILER_REPOSITORY_BACKEND=memory` selects the process-local adapter for isolated development and tests. Its state disappears when the process exits; it is not the normal runtime configuration.

## Modules

~~~text
app/
  api/
    auth.py          login and refresh placeholder
    admin.py         admin users, keys, usage, dashboard
    user.py          authenticated self-service routes
    runtime.py       OpenAI-style runtime route
  repositories/
    base.py          repository and unit-of-work protocols
    memory.py        isolated in-memory adapter
    sqlalchemy.py    durable SQLAlchemy adapter
    dependencies.py adapter injection
  auth.py            JWT and password helpers
  bootstrap.py       SQL demo-seed command
  config.py          TAILER-prefixed settings
  database.py        SQLAlchemy engine/session factory
  demo_seed.py       deterministic records and idempotent seed
  domain.py          persistence-neutral records
  credential_security.py  AES-256-GCM keyring and credential redaction helpers
  key_security.py    key generation, HMAC digest, display prefix
  main.py            app, CORS, routers, liveness/readiness
  models.py          Pydantic API schemas
  models_db.py       SQLAlchemy schemas
  policies.py        provider-independent static request policy decisions
  providers.py       provider protocol plus Mock, OpenAI, and Gemini adapters
  serialization.py   domain-to-API mappings
  services.py        application behavior and transactions
alembic/
  versions/0001_initial_schema.py
  versions/0002_contract_alignment.py
  versions/0003_secure_provider_persistence.py
tests/               dual-adapter API, repository, and migration suite
alembic.ini
main.py
requirements-dev.txt
requirements.txt
~~~

The retired `mock_data.py` globals are not part of the active application.

## API route families

| Credential | Routes |
| --- | --- |
| None | `GET /`, `GET /health`, `GET /ready`, `POST /api/auth/login` |
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

Important TAILER settings include:

- `TAILER_DATABASE_URL`
- `TAILER_REPOSITORY_BACKEND` (`sqlalchemy` by default; `memory` for isolation)
- `TAILER_DEFAULT_PROJECT_ID`
- `TAILER_DEFAULT_PROVIDER`
- `TAILER_REDIS_URL`
- `TAILER_FRONTEND_URL`
- `TAILER_JWT_SECRET_KEY`
- `TAILER_JWT_ALGORITHM`
- `TAILER_JWT_EXPIRATION_MINUTES`
- `TAILER_SUB_API_KEY_PEPPER`
- `TAILER_CREDENTIAL_ENCRYPTION_KEYS` (JSON map of key version to URL-safe
  base64 AES-256 key)
- `TAILER_CREDENTIAL_ACTIVE_KEY_VERSION`
- `TAILER_OPENAI_BASE_URL`
- `TAILER_GEMINI_BASE_URL`
- `TAILER_PROVIDER_TIMEOUT_SECONDS`

Dashboard tokens use the JWT-specific settings. Sub-API-key lookup computes an HMAC with `TAILER_SUB_API_KEY_PEPPER`; changing the pepper invalidates existing keys. `TAILER_SECRET_KEY` is not the provider-credential encryption key.

Generate a provider-credential key from `backend/`:

~~~bash
python -c "from app.credential_security import generate_credential_encryption_key as g; print(g())"
~~~

Put the generated value in an operator-controlled environment or `.env` file;
do not commit it:

~~~dotenv
TAILER_CREDENTIAL_ENCRYPTION_KEYS={"v1":"<generated URL-safe base64 AES-256 key>"}
TAILER_CREDENTIAL_ACTIVE_KEY_VERSION=v1
~~~

The registry may contain older versions while the active version changes for
new writes. Existing rows remain decryptable only while their recorded version
is present. Credential creation and real-provider resolution fail closed when
the keyring is absent, invalid, or cannot decrypt a row. The default empty
keyring is valid only for mock-provider development.

## Persistence and key lifecycle

Alembic resolves its connection through `TAILER_DATABASE_URL`. Revision `0002`
aligns the original API/database contracts. Revision `0003` adds
`provider_credentials` and `model_configs`, including project/provider scope,
credential lifecycle, model-alias uniqueness, enabled state, and non-negative
pricing constraints.

The configured default project receives newly created keys. Key creation generates a high-entropy bearer, returns it once, and persists only its HMAC digest plus a non-secret display prefix. Runtime authorization hashes the presented bearer and performs an indexed digest lookup before policy checks.

The SQLAlchemy unit of work owns one session per transaction. The in-memory adapter uses copy-on-write state, explicit commit/rollback, detached reads, and serialized transactions so its behavior matches SQL closely. Runtime authorization closes its read transaction before provider I/O and writes usage in a separate short transaction.

Nullable per-key request-rate and output-token limits round-trip through both
adapters. The output-token ceiling is enforced before provider-route resolution;
the request-rate value is metadata only until dynamic rate enforcement is added.

`POST|GET /admin/provider-credentials` and
`DELETE /admin/provider-credentials/{credential_id}` accept or manage a secret
but return only its ID, scope, display name, safe suffix hint, key version,
status, and timestamps. Ciphertext and plaintext are never API response fields.
The corresponding `/admin/model-configs` routes create/list/disable alias
routes. Revoking a credential also disables its enabled model configurations.

## Tests

Install test dependencies and run the suite from this directory:

~~~bash
pip install -r requirements-dev.txt
python -m pytest -q
~~~

All 229 tests passed in normal and reversed file order on 2026-08-02. API cases
run against a fresh in-memory store and a fresh Alembic-migrated SQLite
database. Coverage includes seed
idempotency, transaction behavior, HMAC lookup, hash-at-rest, AES-GCM
round-trips/tamper detection/rotation, metadata redaction, model resolution,
mocked-upstream OpenAI and Gemini requests, native Interactions response and
thought-token handling, normalized errors, durable failure events, and live-
smoke orchestration safety. No live backend, PostgreSQL, Redis, or provider
service is required for this suite.

The earlier Iteration 1 checkpoint passed 121 tests in both normal and reversed
file order and included a clean PostgreSQL 16 revision-`0002` round-trip.
Iteration 2 is complete through the verified live Gemini route.

## Verified checks

~~~bash
python -m compileall -q app tests
python -m pytest -q
alembic heads
alembic upgrade head --sql
~~~

The same date includes a clean PostgreSQL 16
upgrade/check/downgrade/re-upgrade at `0003`, a clean backend image build with
`cryptography` 49.0.0, and a healthy four-service Compose restart. A configured
encrypted route to a deliberately non-routable HTTPS upstream produced a
sanitized `provider_unavailable` event that survived backend restart; API,
database inspection, and logs exposed neither plaintext nor ciphertext, and the
probe rows were removed. The final container intentionally uses an empty
keyring and the deterministic mock path. The opt-in Gemini pipeline also
completed twice across backend restart, verified configured nonzero pricing and
durable usage, scanned API/database/log surfaces for secrets, removed exact
probe rows, and restored all four services. See [testing](../docs/testing.md)
for the verification record.
