# TAILER Project Implementation Plan

Last reconciled: 2026-08-02

## Purpose and source-of-truth rules

This file defines delivery order and acceptance gates. It is not evidence that
a feature exists.

- Code and executable tests define behavior.
- `tasks.md` is the active execution queue.
- This plan defines iteration boundaries.
- `docs/architecture.md` defines current and target shape.
- `docs/product.md` defines product scope.
- `docs/archive/` contains historical snapshots only.

## Product outcome

The MVP is a secure gateway in which an admin can configure one project and one
real LLM provider credential, create limited Sub-API keys, route
OpenAI-compatible requests, enforce permissions and budgets before provider
calls, and inspect durable usage.

## Verified current baseline

Verified on 2026-08-02 in the Iteration 2 working tree:

### Application and tests

- Frontend lint and production build pass.
- The 182-case backend suite passes in normal and reversed file order.
- API characterization runs through both the copy-on-write memory adapter and a
  fresh Alembic-migrated SQLAlchemy/SQLite adapter.
- PostgreSQL is the default runtime adapter for active auth, admin, user,
  runtime-key, and usage behavior.
- Passwords are hashed; JWT login/RBAC and configured signing/lifetime work.
- Generated Sub-API keys are HMAC-SHA-256 digests at rest and raw only in the
  creation response. Later API reads and frontend state expose a safe display
  fragment only.
- Active, expiry, project-state, and allowed-model checks occur before provider
  invocation.
- Versioned AES-256-GCM provider credentials and model aliases persist behind
  metadata-only admin APIs. Master-key values are redacted by settings objects.
- The OpenAI Chat Completions adapter uses backend-only credentials, configured
  provider model/pricing, HTTPS, and sanitized typed errors.
- Successful calls and normalized provider failures record durable usage; no
  database transaction remains open during provider I/O.

### Database and runtime

- Alembic revision `0003` passes drift detection, SQLite upgrade/downgrade/
  re-upgrade, scoped credential-FK inspection, legacy-null backfill, and a clean
  PostgreSQL 16 upgrade/check/downgrade/re-upgrade.
- Two simultaneous seed processes against a fresh PostgreSQL database both
  succeed and converge to the deterministic record counts.
- `tailer.cmd start` and `tailer.cmd restart` build the stack and leave
  PostgreSQL, Redis, backend, and frontend healthy.
- Liveness, persistence readiness, frontend access, and admin login pass.
- A created user, revoked key, and usage event survive a complete controller
  restart; the acceptance records were removed afterward.
- Concurrent duplicate-user requests return one success and one 409 conflict.
- SQL echo is disabled by default; acceptance logs contain no raw keys or probe
  identity data.
- A live encrypted credential/model route reached the real OpenAI adapter
  boundary against a deliberately unavailable HTTPS target. Its sanitized
  failure and stable error code survived restart; ciphertext-at-rest and log
  redaction checks passed, and every probe row was removed.

### Operator surface

- `tailer.cmd` provides an interactive Windows menu and command mode.
- `tailer.sh` provides Unix start, stop, restart, status, logs, configuration,
  and help commands.
- `deploy/systemd/tailer.service` delegates boot lifecycle to `tailer.sh` for a
  rootful Docker host installed at `/opt/tailer`.
- Windows and Bash controller checks passed. The unit still needs one live
  installation check on a real systemd/cgroup host; WSL1 could support only a
  structural review.

## Current limitations

- The OpenAI adapter and encrypted credential route are implemented, but a
  successful call with a disposable real OpenAI credential has not been run in
  this environment. The final running stack intentionally has no credential
  keyring configured and therefore fails credential creation closed.
- Demo passwords, deterministic demo bearer keys, and example secrets make the
  current system development-only.
- Request-rate, request-count, token, budget, and per-key maximum-token policies
  are not enforced; Redis is not yet consumed by application code.
- Provider failures are durable. TAILER policy-blocked calls and TAILER-enforced
  rate-limit outcomes are not yet implemented.
- Refresh sessions, key rotation workflow, secure password administration,
  HTTPS, backups, and production secret management remain incomplete.

## Canonical MVP contract decisions

- Dashboard auth API: `/api/auth/*`.
- Admin API: `/admin/*`.
- User API: `/user/*`.
- Runtime API: `/v1/chat/completions`.
- Core persisted tables: `users`, `projects`, `provider_credentials`,
  `model_configs`, `sub_api_keys`, and `usage_events`.
- Do not add organizations to the first MVP; one deployment hosts one configured
  project initially.
- A raw Sub-API key appears only in its creation response. It is never returned
  by list/detail APIs, reconstructed, logged, or persisted.
- Pipelines, multi-organization tenancy, billing, and advanced analytics remain
  deferred until the durable gateway is policy-enforced.

## Iteration 0 — reproducible API contract

Status: complete on 2026-08-02.

Goal: characterize useful behavior, harden invalid boundaries, and make the
migration/runtime scaffold executable before persistence cutover.

Delivered:

- repository/documentation hygiene and a clear active-doc hierarchy;
- deterministic login, RBAC, user, admin, runtime, and migration tests;
- normalized/validated request boundaries and authoritative JWT settings;
- provider forwarding, measured latency, and invalid-metering rejection;
- environment-driven Alembic configuration;
- healthy Compose dependency sequencing and Docker/PostgreSQL verification.

Exit gate: passed. Earlier Docker and PostgreSQL blockers were cleared on
2026-08-02.

## Iteration 1 — persistence vertical slice

Status: complete on 2026-08-02.

Goal: replace direct global-list access with a durable repository boundary while
preserving tested API behavior.

Delivered:

1. Frozen API/domain/ORM mapping for default project, usage aliases, provider
   metadata, key secrecy, seeding, and transaction ownership.
2. Focused user, project, key, and usage repository protocols plus application
   services and an explicit unit of work.
3. Serialized copy-on-write memory adapter with detached records, explicit
   commit/rollback, and constant-time digest comparison.
4. SQLAlchemy adapter with one Session per operation and persistence-conflict
   translation.
5. Alembic revision `0002` for schema/contract alignment and legacy backfills.
6. Deterministic, collision-aware, concurrent-safe, idempotent seed.
7. Full route cutover for auth, admin/user reads and writes, runtime HMAC lookup,
   and durable usage.
8. High-entropy HMAC-at-rest/show-once Sub-API keys and matching frontend flow.
9. Repository readiness health, non-reloading container startup, and quiet SQL
   logs by default.
10. Cross-adapter, migration, transaction, concurrency, secrecy, and restart
    durability evidence.

Exit gate result:

- no active route imports `MOCK_*` or `app.mock_data`;
- clean databases migrate and seed idempotently under concurrent startup;
- contract tests pass through both adapters;
- user/key mutations, revocation, and usage survive restart;
- normal read APIs, persistence, and logs contain no raw Sub-API key;
- transaction and rollback behavior is executable and documented.

Gate: passed.

## Iteration 2 — secure real-provider gateway (acceptance pending)

Status: implementation complete on 2026-08-02; one external live-success gate
remains open.

Goal: route one real provider safely without exposing its credential.

Delivered:

1. Versioned AES-256-GCM credential encryption with a redacted external keyring,
   active key version, rotation primitive, and AAD bound to credential, project,
   provider, and key version.
2. `provider_credentials` and `model_configs` repository/ORM persistence plus
   Alembic revision `0003` and a scoped composite credential foreign key.
3. Metadata-only admin create/list/revoke credential APIs and create/list/disable
   model-configuration APIs.
4. Public model-alias resolution to an active credential, provider model, and
   exact per-million-token EUR pricing.
5. An HTTPS OpenAI Chat Completions adapter behind the provider boundary while
   retaining deterministic `MockProvider` injection.
6. Sanitized timeout, connectivity, authentication, permission, not-found,
   rate-limit, rejected-request, and invalid-response failures.
7. Separate durable success/failure usage transactions with stable error codes.
8. Cross-adapter encryption, redaction, routing, adapter, failure, transaction,
   migration, deterministic-mock, HTTPS, and log-safety tests plus an
   environment-only operator smoke procedure.

Exit gate result:

- passed: database, API, frontend payloads, and logs contain no raw provider or
  Sub-API secret;
- pending: one configured completion against the real OpenAI service, because no
  disposable provider credential was available;
- passed: provider errors are normalized and durable;
- passed: `MockProvider` remains deterministic for tests;
- passed: all earlier regression, migration, Compose, and restart gates remain
  green.

Task 7 and this iteration remain open only for the disposable live OpenAI
success smoke. Do not start the policy iteration by treating mocked-upstream or
unavailable-upstream evidence as that success.

The Sub-API-key HMAC/show-once work formerly scheduled here was pulled forward
and completed in Iteration 1.

## Iteration 3 — enforced policy

Goal: prevent unauthorized spend before provider calls.

Delivery order:

1. Configured model aliases and per-key allow lists
2. Max tokens per request
3. Per-minute and daily request limits
4. Token and cost budgets
5. Redis atomic counters with PostgreSQL as durable truth
6. Durable blocked and rate-limited audit events

Exit gate:

- every denial has a stable error code;
- tests prove the provider is not called for denied requests;
- concurrent requests cannot trivially bypass limits;
- admin and user views reflect success, failure, blocked, and rate-limited
  outcomes.

## Iteration 4 — product surface and delivery

Deliverables:

- project/provider/model management UI;
- user integration examples and allowed-model view;
- admin usage/error views and CSV export;
- key/provider rotation workflows;
- production validation, HTTPS, backup/restore, structured logs, and monitoring;
- live systemd-host verification and complete operator runbook.

Exit gate: a new operator can deploy one project, add one provider credential,
issue a safe Sub-API key, make a real completion, observe durable usage, enforce
a limit, revoke access, and recover the service from a documented backup.

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

The MVP is complete when tests or an operator runbook demonstrate:

- admin authentication and authorization;
- one persisted project and encrypted provider credential;
- hash-at-rest, show-once Sub-API-key lifecycle;
- one real-provider completion through `/v1/chat/completions`;
- model and spend policy enforced before provider invocation;
- durable success, failure, blocked, and rate-limited usage/audit events;
- admin and user usage visibility;
- key revocation and credential rotation;
- repeatable deployment, migration, backup, restore, and secret handling.
