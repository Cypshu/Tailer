# TAILER Agent Tasks

Last reconciled: 2026-08-02

This is the sole active execution board. Read `AGENTS.md` first and use `TAILER_Project_Implementation_Plan.md` for iteration context.

## Status key

- `[ ]` ready or not started
- `[~]` in progress
- `[x]` complete
- `[!]` blocked by a concrete external condition

Only one task should normally be marked in progress.

## Workspace warning

- Local `main` is ahead of `origin/main` and has substantial pre-existing tracked and untracked work.
- Preserve unrelated changes; do not blanket-clean, reset, or stage the repository.
- `.claude/worktrees/` contains three registered branches with commits not merged into `main`:
  - `worktree-fix-scripts`
  - `worktree-test-subkey`
  - `worktree-test-subkey-run`
- Do not delete those directories directly. Reconcile through Git worktree and branch operations in a separately authorized task.
- `.tailer-runs/` is generated local harness output, not the canonical test suite.

## Verified baseline

Passed on 2026-08-02:

- `frontend: npm run lint`
- `frontend: npm run build`
- `backend: python -m pytest -q` — 48 passed
- `backend: reversed test-file order` — 48 passed
- `backend: python -m compileall -q app tests`
- live backend login/RBAC/user/runtime smoke flow
- `docker compose config --quiet`
- `backend: alembic upgrade head --sql`
- disposable SQLite Alembic upgrade/downgrade/re-upgrade and drift check

Not verified:

- full Compose startup; Docker daemon unavailable
- online PostgreSQL Alembic upgrade/downgrade; Docker daemon and local PostgreSQL are unavailable

## Implemented iteration: reproducible API contract

### 0. Repository and documentation preparation

- Status: `[x]`
- Goal: make the next task discoverable and remove misleading project clutter.

Completed:

- Audited all distinct project Markdown content, including ignored worktree snapshots.
- Consolidated active documentation and archived dated summaries.
- Added safe Docker build-context and ignore hygiene.
- Preserved registered worktrees and the generated run harness.
- Removed the unused frontend mock-data duplicate and the assertion-free loose runtime demo.
- Corrected landing-page and admin-action text that claimed unavailable behavior.
- Recorded verified and unverified baseline facts.
- Selected contract tests before persistence as the next implementation step.

### 1. Backend characterization test suite

- Status: `[x]`
- Priority: P0
- Goal: create a deterministic regression contract for current auth and runtime behavior.

Files:

- `backend/requirements-dev.txt`
- `backend/tests/conftest.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_admin.py`
- `backend/tests/test_runtime.py`
- `backend/tests/test_migrations.py`

Tasks:

- [x] Add compatible `pytest` and `httpx` development dependencies.
- [x] Build a FastAPI `TestClient` fixture.
- [x] Reset mock users, projects, keys, usage events, dependency overrides, and provider state around every test.
- [x] Test valid and invalid login.
- [x] Test anonymous admin 401 and user admin 403.
- [x] Test authenticated user identity and key scoping.
- [x] Test valid, invalid, revoked, expired, malformed-expiry, and model-forbidden runtime keys.
- [x] Test successful usage-event delta.
- [x] Test that pre-provider rejections do not add a success event.
- [x] Remove the loose root runtime demo so pytest collection is unambiguous.

Acceptance:

- `cd backend && python -m pytest` passes without live services.
- Two consecutive runs pass in either order.
- Tests do not leak mutations into later tests.
- The suite fails when a protected behavior is deliberately broken.

Evidence: 48 tests passed in normal and reversed file order without live services. The migration test uses its own temporary SQLite database.

### 2. Request-boundary and JWT configuration hardening

- Status: `[x]`
- Priority: P0
- Depends on: Task 1
- Goal: reject invalid data and make declared auth configuration truthful.

Tasks:

- [x] Validate and normalize email.
- [x] Return a conflict for duplicate email.
- [x] Require an existing owner for new keys.
- [x] Require non-empty allowed models.
- [x] Require positive limits and budget values.
- [x] Parse and require a future expiry.
- [x] Type and validate chat messages.
- [x] Require positive `max_tokens` and bounded temperature.
- [x] Reject expired keys before provider invocation.
- [x] Forward supported runtime options.
- [x] Measure latency instead of storing a constant.
- [x] Use the declared JWT secret, algorithm, and expiration settings.
- [x] Add tests for every rule.

Acceptance:

- Invalid payloads return stable 4xx responses.
- Negative or rejected requests cannot create successful usage.
- Existing happy-path contract tests remain green.

### 3. Alembic and Compose runtime verification

- Status: `[!]`
- Priority: P0
- Depends on: Task 1
- Goal: make the persistence scaffold executable from documented configuration.

Tasks:

- [x] Remove the obsolete Compose `version` field and revalidate configuration rendering.
- [x] Make Alembic consume the configured database URL.
- [x] Remove the hardcoded URL mismatch.
- [x] Add a disposable SQLite upgrade/downgrade/re-upgrade regression test.
- [ ] Verify upgrade, downgrade, and re-upgrade on a clean PostgreSQL database — blocked: Docker daemon and local PostgreSQL unavailable.
- [ ] Verify full Compose startup — blocked: Docker daemon unavailable.
- [x] Record exact commands and results in `docs/testing.md`.
- [x] Add backend/frontend health checks and dependency sequencing to Compose.

Acceptance:

- A clean database reaches Alembic head and round-trips safely.
- Backend health and frontend access work through Compose.
- No obsolete Compose configuration warning remains.

The implementation portion is complete. Iteration 0 exits under its concrete-external-blocker clause; Task 6 must not cut over to PostgreSQL until the two Docker-backed checks above pass.

## Next iteration: persistence vertical slice

### 4. Freeze API-to-ORM mappings — NEXT

- Status: `[ ]`
- Priority: P1
- Depends on: Task 1 and Task 3 configuration work. The documented Docker verification blocker does not prevent this design-only task.

Decisions required:

- [ ] Default project and `project_id` behavior
- [ ] create-only raw key versus stored hash/prefix
- [ ] usage field mapping and required provider/project fields
- [ ] idempotent demo seed behavior
- [ ] transaction and repository boundaries

Acceptance:

- `docs/architecture.md` records one unambiguous mapping.
- Migration, ORM, Pydantic, and endpoint contracts agree.

### 5. Repository boundary with in-memory adapter

- Status: `[ ]`
- Priority: P1
- Depends on: Tasks 1 and 4

Tasks:

- [ ] Define focused repositories/services for users, projects, keys, and usage.
- [ ] Wrap the current mock store behind an adapter.
- [ ] Inject repositories into auth/admin/user/runtime routes.
- [ ] Remove direct global-list imports from route modules.
- [ ] Keep all characterization tests green.

Acceptance:

- Routes depend on repository/service interfaces.
- Current behavior is unchanged.
- Mock state remains usable for isolated tests.

### 6. SQLAlchemy adapter and durable cutover

- Status: `[ ]`
- Priority: P1
- Depends on: Tasks 3, 4, and 5

Tasks:

- [ ] Add idempotent demo seed.
- [ ] Implement SQLAlchemy repositories.
- [ ] Cut over auth and user lookup.
- [ ] Cut over admin reads and writes.
- [ ] Cut over runtime key lookup and usage writes.
- [ ] Add PostgreSQL integration and restart-durability tests.

Acceptance:

- No active route reads `MOCK_*` directly.
- Mutations and usage survive restart.
- Contract tests pass against both adapters.

## Later queue

### 7. Secure provider and Sub-API-key lifecycle

- Status: `[ ]`
- Priority: P2
- Outcome: encrypted provider credentials, hash-at-rest keys, show-once creation, one real adapter.

### 8. Model configuration and policy enforcement

- Status: `[ ]`
- Priority: P2
- Outcome: aliases, expiration, request/token/cost limits, and provider-not-called guarantees.

### 9. Durable usage and audit behavior

- Status: `[ ]`
- Priority: P2
- Outcome: success, failure, and blocked events with trustworthy latency and cost.

### 10. Project and dashboard completion

- Status: `[ ]`
- Priority: P3
- Outcome: project/provider/model surfaces, truthful user integration help, and admin reporting.

### 11. Deployment preparation

- Status: `[ ]`
- Priority: P3
- Outcome: production configuration, migrations, HTTPS, backups, logs, and operator guide.

## Deferred

Pipelines, multi-organization tenancy, billing, advanced analytics, RAG, and agent orchestration remain deferred until the core MVP gate in the implementation plan is met.

## Compact completed log

- Standalone repository and Docker-oriented service layout
- Frontend/backend read and write integration
- Admin dashboard correctness pass
- JWT login and basic RBAC
- Mock provider/runtime boundary
- Persistence model and Alembic scaffold
- Deterministic 48-case backend regression suite
- Request-boundary, expiry, metering, and JWT configuration hardening
- Environment-driven Alembic configuration and Compose health sequencing
- Frontend build repair and form-field readability
- Documentation and repository-hygiene preparation
