# TAILER Agent Tasks

Last reconciled: 2026-08-02

This is the sole active execution board. Read `AGENTS.md` first and use
`TAILER_Project_Implementation_Plan.md` for iteration context.

## Status key

- `[ ]` ready or not started
- `[~]` in progress
- `[x]` complete
- `[!]` blocked by a concrete external condition

Only one task should normally be marked in progress.

## Workspace warning

- Iterations 1 and 2 are present as uncommitted work in the root worktree. Preserve them;
  do not blanket-clean, reset, checkout, or stage unrelated files.
- Root `main` matched `origin/main` at commit `29828c8` before this iteration.
- `.claude/worktrees/` contains registered branches with unmerged commits.
  Reconcile them through Git worktree/branch operations only in a separately
  authorized task; never delete their directories directly.
- `.tailer-runs/` is ignored generated output, not the canonical test suite.

## Verified baseline

Passed on 2026-08-02:

- `frontend: npm run lint`
- `frontend: npm run build`
- `backend: python -m compileall -q app tests`
- `backend: python -m pytest -q` — 182 passed
- `backend: reversed test-file order` — 182 passed
- `tailer.cmd config` and `docker compose config --quiet`
- Alembic head `0003`, drift check, SQLite round-trip/scoped-FK inspection,
  legacy backfill, and clean PostgreSQL 16 upgrade/check/downgrade/re-upgrade
- fresh PostgreSQL concurrent demo bootstrap — both processes succeeded and
  converged to 3 users, 1 project, 3 keys, and 4 usage events
- `tailer.cmd start` and `tailer.cmd restart` — PostgreSQL, Redis, backend, and
  frontend all healthy
- live liveness, repository readiness, frontend, and admin-login checks
- live restart durability for a created user, revoked key, and usage event
- live concurrent duplicate-user result of one 200 and one 409
- raw creation key absent from later API reads, PostgreSQL, and backend logs
- encrypted provider credential/model APIs, real OpenAI adapter routing, and
  durable sanitized provider-failure usage passed isolated and live probes
- live encrypted credential ciphertext, unavailable-upstream failure, restart
  durability, and log redaction passed; exact provider/key/usage probes were
  removed afterward
- probe rows/databases removed after acceptance; the development stack remains
  running and healthy

Known validation limitation: the systemd unit passed structural review, but a
live systemd/cgroup host was unavailable under WSL1. Verify installation and
boot behavior on the target Linux host. A successful completion against the
real OpenAI service also awaits an environment-supplied disposable credential.

## Completed foundation

### 0. Repository and documentation preparation

- Status: `[x]`
- Active documentation has a source-of-truth hierarchy and dated material is
  archived.
- Docker contexts and generated-output ignores are in place.
- Registered worktrees were preserved.
- The obsolete frontend duplicate data and loose runtime demo were removed.

### 1. Reproducible API contract

- Status: `[x]`
- Deterministic FastAPI tests cover login, RBAC, user scoping, runtime key
  authorization, provider forwarding, usage, and invalid boundaries.
- Every client contract runs against both a fresh copy-on-write memory adapter
  and a fresh Alembic-migrated SQLAlchemy/SQLite adapter.
- Tests pass in normal and reversed order without live services.

### 2. Request, auth, and metering hardening

- Status: `[x]`
- Email normalization, duplicate conflict, owner existence, future expiry,
  positive limits, typed messages, positive `max_tokens`, and temperature bounds
  are enforced.
- JWT settings are authoritative.
- Expiry/model denial occurs before provider invocation.
- Supported provider options, measured latency, and invalid-metering rejection
  are tested.
- Usage pagination is bounded consistently across adapters.

### 3. Alembic and Compose runtime readiness

- Status: `[x]`
- Alembic consumes `TAILER_DATABASE_URL` and revision `0002` aligns ORM and API
  contracts, constraints, UTC timestamps, exact money, provider-model/currency,
  and non-null latency.
- PostgreSQL and Redis gate backend startup; backend repository readiness gates
  frontend startup.
- The container migrates and seeds before starting non-reloading Uvicorn.
- `/health` is liveness and `/ready` checks repository connectivity.

## Completed Iteration 1 — persistence vertical slice

### 4. Freeze API-to-ORM mappings

- Status: `[x]`
- Default project, usage aliases, required provider metadata, seed behavior,
  session lifetime, and transaction ownership are frozen in
  `docs/architecture.md`.
- A raw Sub-API key is creation-only. Later reads expose `key_prefix`; storage
  contains only a peppered HMAC-SHA-256 digest and safe display fragment.

### 5. Repository boundary and in-memory adapter

- Status: `[x]`
- Focused user, project, key, and usage repositories sit behind an explicit
  unit of work and application service.
- Auth/admin/user/runtime routes no longer import global mock lists.
- The memory adapter uses serialized copy-on-write transactions, detached
  records, explicit commit/rollback semantics, and constant-time digest compare.
- The obsolete `backend/app/mock_data.py` was removed.

### 6. SQLAlchemy adapter and durable cutover

- Status: `[x]`
- SQLAlchemy repositories back all active route behavior by default.
- The demo seed is deterministic, collision-aware, idempotent, concurrent-start
  tolerant, and does not silently rewrite hashes after pepper rotation.
- Persistence constraint conflicts are translated at the service boundary;
  duplicate user creation returns 409 instead of leaking an integrity failure.
- Runtime authorization closes its read transaction before provider I/O and
  records successful usage in a separate short transaction.
- User/key writes, revocation, and usage survive a complete controller restart.
- Backend and frontend implement the show-once key flow end to end.

Iteration 1 exit gate: passed on 2026-08-02.

## Active iteration

### 7. Secure provider credential and real-adapter slice — IN PROGRESS

- Status: `[~]`
- Priority: P2
- Depends on: completed Iteration 1
- Goal: route one real provider without exposing its credential.

Tasks:

- [x] Freeze the provider-credential encryption/key-management contract.
- [x] Add `provider_credentials` and the minimum `model_configs` schema through
  a new Alembic revision.
- [x] Add admin create/list/delete credential APIs; reveal no raw secret or
  ciphertext in read responses.
- [x] Implement one real provider adapter behind `backend/app/providers.py`.
- [x] Resolve a public model alias to provider, provider model, and credential.
- [x] Normalize upstream timeouts, authentication, rate-limit, and response
  failures without leaking prompt or secret data.
- [x] Persist success and provider-failure usage with stable status/error data.
- [x] Keep `MockProvider` as the deterministic test adapter.
- [x] Add tests for encryption-at-rest, redaction, adapter requests, normalized
  errors, transaction lifetime, and log safety.
- [x] Add an operator smoke flow that uses an environment-supplied disposable
  provider credential; never add a real credential to the repository.

Acceptance status:

- [x] Database, API responses, frontend payloads, and logs contain neither the raw
  provider credential nor raw Sub-API keys.
- [!] A configured real-provider completion succeeds through
  `/v1/chat/completions`.
- [x] Provider failures are durable and normalized.
- [x] All earlier regression tests remain green and the expanded 182-case suite
  passes in normal and reversed file order.

Implementation, security, PostgreSQL revision `0003`, clean-image Compose,
restart, encryption-at-rest, failure durability, and log-redaction gates pass.
The only open exit-gate item is a successful request using an
environment-supplied disposable OpenAI credential; no such credential was
available in this environment. Keep Task 7 in progress until that smoke passes.

The Sub-API-key hash-at-rest/show-once work originally planned here was pulled
forward and completed in Iteration 1; do not reimplement it.

## Later queue

### 8. Model policy enforcement

- Status: `[ ]`
- Priority: P2
- Outcome: model aliases, max tokens, per-minute/daily requests, token and cost
  budgets, provider-not-called guarantees, and Redis concurrency safety.

### 9. Durable audit behavior

- Status: `[ ]`
- Priority: P2
- Outcome: success, provider failure, blocked, and rate-limited events with
  stable error codes, trustworthy latency/cost, and retention rules.

### 10. Project and dashboard completion

- Status: `[ ]`
- Priority: P3
- Outcome: project/provider/model management, honest integration help, admin
  usage/error views, and CSV export.

### 11. Deployment preparation

- Status: `[ ]`
- Priority: P3
- Outcome: production configuration validation, HTTPS, backup/restore, logs,
  secret rotation, systemd host verification, and an operator runbook.

## Deferred

Pipelines, multi-organization tenancy, billing, advanced analytics, RAG, and
agent orchestration remain deferred until the core MVP gate in the implementation
plan is met.
