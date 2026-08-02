# TAILER Project Implementation Plan

Last reconciled: 2026-08-02

## Purpose and source-of-truth rules

This file defines delivery order and acceptance gates. It is not evidence that a feature exists.

- Code and executable tests define behavior.
- `tasks.md` is the active execution queue.
- This plan defines iteration boundaries.
- `docs/architecture.md` defines the target shape.
- `docs/product.md` defines product scope.
- `docs/archive/` contains historical snapshots only.

## Product outcome

The MVP is a secure gateway in which an admin can configure one project and one real LLM provider credential, create limited Sub-API keys, route OpenAI-compatible requests, enforce permissions and budgets before provider calls, and inspect durable usage.

## Verified baseline

Verified on 2026-08-02 from local `main` at commit `d08d5b9` plus an existing dirty worktree:

### Passing

- Frontend lint and production build
- Backend 48-test suite in normal and reversed file order
- Backend live smoke path:
  - health
  - admin and user login
  - admin RBAC success
  - user-to-admin denial
  - user identity
  - valid runtime request
  - invalid runtime key denial
- Docker Compose configuration rendering
- Alembic head discovery and offline upgrade SQL generation
- Disposable SQLite migration upgrade/downgrade/re-upgrade and schema-drift check

### Implemented but development-only

- JWT dashboard authentication over mock users
- Admin/user route protection
- In-memory user and key creation/revocation
- Raw Sub-API-key lookup with active, expiry, and allowed-model checks
- Mock provider completion
- In-memory successful-request usage append
- SQLAlchemy/Alembic scaffold with no active route consumers

### Not verified or not implemented

- Online PostgreSQL Alembic upgrade/downgrade was not verified because neither Docker nor a local PostgreSQL server was available.
- Full Compose startup was not verified because the Docker daemon was unavailable.
- Active routes are not persistence-backed.
- Request count, token, budget, and per-key max-token policy are not enforced.
- Raw Sub-API keys are returned by read APIs.
- Only successful runtime calls create usage events.
- No real provider or provider credential encryption exists.

## Canonical MVP contract decisions

These decisions remove conflicts in older planning documents:

- Dashboard auth API: `/api/auth/*`.
- Admin API: `/admin/*`.
- User API: `/user/*`.
- Runtime API: `/v1/chat/completions`.
- Core persisted tables: `users`, `projects`, `sub_api_keys`, and `usage_events`.
- Add `provider_credentials` and `model_configs` only in the secure-provider slice.
- Do not add organizations to the first MVP; one deployment may host one project initially.
- Preserve current response shapes during persistence work unless a versioned contract change is approved.
- A raw Sub-API key may appear only in its creation response after the security slice.
- Pipelines, multi-organization tenancy, billing, and advanced analytics are deferred until the core gateway is durable and policy-enforced.

## Iteration 0 — Reproducible API contract (implemented)

Status: implementation complete on 2026-08-02. PostgreSQL and full Compose runtime verification remain recorded external blockers; the next executable task is Task 4 in `tasks.md`.

Goal: protect the existing useful behavior with deterministic tests, then harden invalid boundaries before persistence changes.

### I0.1 Repository and documentation hygiene

Status: completed in the 2026-08-02 preparation pass.

Outcomes:

- Active docs were reduced to a clear hierarchy.
- Stale reports were moved under `docs/archive/`.
- Generated run output is ignored.
- Docker build contexts exclude local dependencies and caches.
- The unused frontend mock-data duplicate was removed.
- Registered unmerged Git worktrees were preserved.

### I0.2 Backend characterization suite

Status: completed.

Create:

- `backend/requirements-dev.txt`
- `backend/tests/conftest.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_admin.py`
- `backend/tests/test_runtime.py`
- `backend/tests/test_migrations.py`

Required coverage:

- valid and invalid login
- anonymous admin request returns 401
- normal user admin request returns 403
- authenticated `/user/me` identity
- valid Sub-API key completion
- invalid, revoked, and model-forbidden key paths
- one usage event added after success
- no success event added after rejected pre-provider requests
- fixture reset makes tests order-independent

Use FastAPI `TestClient` with `httpx`. Do not promote a live `requests` demo as the regression layer.

Result: 48 tests pass without live services in both normal and reversed file order. Fixtures restore mutable mock and provider state for each test.

### I0.3 Boundary and configuration hardening

Status: completed.

Implement and test:

- valid normalized email and duplicate-email conflict
- existing key owner requirement
- non-empty allowed-model list
- positive request/token/budget limits
- typed future expiration
- non-empty typed chat messages
- positive `max_tokens` and bounded temperature
- expiration rejection before provider invocation
- real latency measurement
- forwarding of supported request fields
- `jwt_secret_key`, `jwt_algorithm`, and `jwt_expiration_minutes` as authoritative settings

Do not redesign raw-key persistence in this slice.

Result: request/admin boundaries return tested 4xx responses, expiry/model checks occur before provider access, provider options and measured latency are recorded, invalid metering cannot create a success event, and JWT settings are authoritative.

### I0.4 Migration and startup readiness

Status: implementation complete; Docker-backed verification blocked by the unavailable daemon.

Implement and verify:

- Alembic reads the configured database URL rather than a hardcoded URL.
- A clean PostgreSQL database can run upgrade, downgrade, and upgrade.
- Setup docs state exact local and Docker commands.
- Full Compose startup reaches a healthy backend and usable frontend.
- Validation evidence records date, command, and environment.

Result: Alembic reads `TAILER_DATABASE_URL`; offline SQL and a disposable SQLite round-trip/drift check pass. Compose rendering passes and all services now have health sequencing. A clean PostgreSQL round-trip and full startup remain unverified until Docker is available.

### Iteration 0 exit gate

- `python -m pytest` passes without a live PostgreSQL, Redis, or backend process.
- Tests are repeatable in any order.
- Invalid payloads cannot create negative or successful usage.
- `npm run lint` and `npm run build` pass.
- `docker compose config --quiet` passes without obsolete configuration warnings.
- Online migration round-trip and Compose startup are either verified or recorded with a concrete external blocker.
- Active docs describe only verified behavior.

Gate result: passed under the explicit concrete-external-blocker clause. Task 6 remains gated on completing PostgreSQL and Compose runtime verification.

### Iteration 0 non-goals

- Postgres route conversion
- raw-key lifecycle redesign
- provider credential storage
- real upstream provider
- Redis quotas
- frontend component tests

## Iteration 1 — Persistence vertical slice (next)

Status: ready for the Task 4 design pass.

Goal: replace direct global-list access while preserving the tested API contract.

### Design prerequisites

Resolve these mappings explicitly before coding:

- API `SubApiKey.key` versus ORM `key_hash` and `key_prefix`
- API keys without `project_id` versus the ORM-required project relation
- API usage `timestamp` and `sub_key_id` versus ORM `created_at` and `sub_api_key_id`
- ORM-required usage `project_id` and `provider`
- idempotent demo seed behavior
- transaction ownership and session lifetime

### Delivery sequence

1. Record the agreed schema/API mapping in `docs/architecture.md`.
2. Add repository interfaces for users, keys, projects, and usage.
3. Add an in-memory adapter and move routes behind it first.
4. Add a SQLAlchemy adapter and idempotent demo seed.
5. Cut over auth, then admin/user reads, admin writes, runtime key lookup, and usage writes one vertical slice at a time.
6. Add restart-durability integration tests.

### Exit gate

- No active route imports `MOCK_USERS`, `MOCK_KEYS`, or `MOCK_USAGE_EVENTS` directly.
- A clean database can be migrated and seeded idempotently.
- Existing API contract tests pass against both in-memory and PostgreSQL adapters.
- User/key mutations and usage survive backend restart.
- Rollback behavior is documented.

## Iteration 2 — Secure real-provider gateway

Goal: route one real provider safely.

Deliverables:

- encrypted provider credential model and service
- create/list/delete admin endpoints that never return raw provider secrets
- cryptographically random Sub-API keys
- key hash and prefix storage
- full key shown only in the creation response
- constant-time key verification
- one configured real provider adapter behind the existing boundary
- normalized provider errors and token usage
- durable success and failure usage events

Exit gate:

- Database and logs contain no raw provider or Sub-API secrets.
- A normal key read returns prefix/metadata only.
- A configured provider call succeeds through the gateway.
- Provider errors are metered without leaking secrets.
- The mock provider remains available for tests.

## Iteration 3 — Enforced policy

Goal: prevent unauthorized spend before provider calls.

Delivery order:

1. Key status and expiration
2. Configured model aliases and per-key allow lists
3. Max tokens per request
4. Per-minute and daily request limits
5. Token and cost budgets
6. Redis counters with PostgreSQL as durable truth

Exit gate:

- Every denial has a stable error code.
- Tests prove the provider is not called for denied requests.
- Concurrent requests cannot trivially bypass limits.
- Admin and user usage views reflect blocked and failed events.

## Iteration 4 — Product surface and delivery

Deliverables:

- project management
- provider and model configuration UI
- truthful key creation/show-once flow
- user integration examples and allowed-model view
- admin usage/error views
- CSV export
- production configuration, HTTPS plan, backups, and logging
- deployment and operator documentation

Exit gate:

A new operator can deploy one project, add one provider credential, issue a safe Sub-API key, make a real completion, observe durable usage, enforce a limit, and revoke access.

## Deferred

Do not schedule these before Iteration 4 exits:

- pipeline engine
- multi-organization tenancy
- billing or Stripe
- advanced RAG or agent workflows
- provider marketplace
- enterprise SSO
- advanced analytics

## MVP definition of done

The MVP is complete when all of the following are demonstrated by tests or an operator runbook:

- Admin authentication and authorization
- One persisted project and provider credential
- Hash-at-rest, show-once Sub-API-key lifecycle
- One real-provider completion through `/v1/chat/completions`
- Model and spend policy enforced before the provider call
- Durable success, failure, and blocked usage events
- Admin and user usage visibility
- Key revocation
- Repeatable local deployment and migration flow
