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
- Active auth, admin, user, runtime, and usage behavior reads and mutates `backend/app/mock_data.py`.
- `backend/app/database.py`, `backend/app/models_db.py`, and `backend/alembic/` are inactive persistence scaffolding.
- The provider boundary exists, but only `MockProvider` is implemented.
- Raw demo keys and display-name passwords make this development-only software.

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
- Never expose an upstream provider key to the frontend or API clients.
- Validate policy before calling a provider.
- Treat Sub-API keys as limited bearer credentials.
- The target lifecycle is hash-at-rest and show-once; the current raw-key behavior is a known gap.
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

# Migration generation without a database
cd backend
alembic upgrade head --sql
~~~

Install `backend/requirements-dev.txt` before running the backend suite. The next implementation task is to freeze the API-to-ORM mapping in Task 4; do not cut routes over to persistence until those decisions are recorded. PostgreSQL migration and full Compose verification remain blocked until a Docker daemon is available.

## Completion standard

A task is complete only when:

- its stated acceptance criteria are met;
- relevant validation passes;
- no unrelated user changes were overwritten;
- behavior and active documentation agree;
- remaining risks are recorded in `tasks.md`.
