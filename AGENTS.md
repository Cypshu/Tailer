# TAILER Agent Guide

This file is the shared entrypoint for coding agents working in this repository.

## Source-of-truth order

When documents disagree, use this order:

1. Executable code and tests
2. `tasks.md` for active work
3. `TAILER_Project_Implementation_Plan.md` for sequencing and acceptance
4. `docs/architecture.md` and `docs/product.md` for target design
5. Files under `docs/archive/` only as historical evidence

Do not infer completed behavior from an architecture or archived summary.

## Current baseline

- Frontend: Next.js 16.2.10 and React 19.2.4.
- Backend: FastAPI 0.115.0 and Pydantic 2.11.7.
- Dashboard auth uses JWT bearer tokens.
- Runtime auth uses a distinct TAILER Sub-API bearer key.
- Request models validate normalized email, positive limits, future expiry, and typed chat input.
- Runtime requests enforce active/expiry/model checks before invoking the provider.
- Active auth, admin, user, runtime, and usage behavior goes through services and repository/unit-of-work interfaces.
- SQLAlchemy/PostgreSQL is the default runtime repository; the in-memory adapter is retained for isolated tests.
- The backend container migrates to Alembic head and applies an idempotent demo seed before serving requests.
- `/health` is process liveness; `/ready` verifies that the configured repository can answer a query and is used by Compose.
- Raw Sub-API keys are returned only by creation. Persistence stores a peppered HMAC-SHA-256 digest and a safe display prefix.
- Provider credentials are encrypted with a versioned AES-256-GCM keyring and
  associated data binding the ciphertext to its credential, project, provider,
  and key version. Admin APIs expose metadata only.
- Alembic head `0003` adds `provider_credentials` and `model_configs`; runtime
  model aliases resolve provider models, credentials, and configured EUR pricing.
- `OpenAIProvider` implements Chat Completions and `GeminiProvider` implements
  stable native Interactions with `store=false`. Both normalize sanitized
  failures. Provider failures are durably recorded with a stable `error_code`;
  the deterministic mock fallback remains active for the unconfigured demo seed.
- Provider-management UI, rate limits, token budgets, cost budgets, per-key
  maximum-token enforcement, and blocked-request audit writes are not implemented.
- Deterministic demo keys in source, display-name passwords, and development secrets make this development-only software.
- The 229-case backend suite runs API contracts against memory and fresh
  Alembic-migrated SQLite adapters without live services, including OpenAI and
  Gemini adapters exercised against mocked upstreams and smoke-orchestration
  safety tests.
- A disposable PostgreSQL 16 round-trip reaches head `0003`. The live Compose
  stack has also exercised a durable sanitized `provider_unavailable` event
  across restart without secret/ciphertext leakage.
- The opt-in Gemini smoke completed twice through the encrypted route, across a
  backend restart, with durable metering, redaction, exact cleanup, and complete
  stack restoration. Iteration 2 is complete; Iteration 3 policy enforcement is
  next. The final stack is healthy with an intentionally empty keyring.
- `tailer.cmd` and `tailer.sh` are the canonical Compose lifecycle controllers
  and expose the explicit `gemini-smoke` verification command. The systemd unit
  under `deploy/systemd/` delegates ordinary lifecycle to `tailer.sh`.

## Before editing

1. Run `git status --short --branch` and preserve unrelated work.
2. Read `tasks.md` and select the explicitly named task or the first ready task.
3. Read only the relevant source and active docs.
4. For frontend changes, also read `frontend/AGENTS.md` and the relevant installed Next.js 16 guide under `frontend/node_modules/next/dist/docs/`.
5. Keep endpoint behavior compatible unless the task explicitly changes the contract.
6. Update `tasks.md` and the implementation plan only when verified facts or sequencing change.

The root worktree may be dirty. Never use blanket clean, reset, checkout, or recursive deletion commands.

## Local worktree warning

`.claude/worktrees/` contains registered Git worktrees on branches with commits not merged into `main`. Treat those directories as separate checkouts, not as duplicate folders to delete. Inspect `git worktree list` and branch history before any cleanup.

`.tailer-runs/` is generated local harness output and is ignored. It is not the regression test suite.

## Security invariants

- Never add real provider credentials, private tokens, or production secrets.
- `.gemini_api` is an ignored, local, disposable test input. Never print, stage,
  copy into Docker configuration, or reuse its value as a production secret.
- Never expose an upstream provider key to the frontend or API clients.
- Never log provider secrets or return stored credential ciphertext. Provider
  credential list/create/revoke responses must remain metadata-only.
- Keep every credential-encryption key version needed by stored rows; new
  writes use `TAILER_CREDENTIAL_ACTIVE_KEY_VERSION`.
- Validate policy before calling a provider.
- Treat Sub-API keys as limited bearer credentials.
- Preserve the hash-at-rest, show-once Sub-API-key lifecycle. Never add a raw bearer to list/detail responses, storage, or logs.
- Treat `TAILER_SUB_API_KEY_PEPPER` as a credential: changing it invalidates existing bearer keys.
- Do not claim limits, persistence, encryption, or real-provider routing without executable evidence.

## Validation baseline

Run checks proportional to the change:

~~~bash
# Frontend
cd frontend
npm run lint
npm run build

# Backend syntax
cd backend
python -m compileall -q app
python -m pytest

# Infrastructure shape
docker compose config --quiet
./tailer.sh config

# Migration generation without a database
cd backend
alembic upgrade head --sql
~~~

On Windows, use `tailer.cmd config` instead of the shell controller. Install `backend/requirements-dev.txt` before running the backend suite. Its API tests execute against both a fresh in-memory store and a fresh Alembic-migrated SQLite database; PostgreSQL is still required for runtime/Compose verification. Read `tasks.md` for the next implementation task rather than inferring it from older summaries.

## Completion standard

A task is complete only when:

- its stated acceptance criteria are met;
- relevant validation passes;
- no unrelated user changes were overwritten;
- behavior and active documentation agree;
- remaining risks are recorded in `tasks.md`.
