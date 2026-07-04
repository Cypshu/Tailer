# TAILER Agent Tasks

Use this file as the direct task board for active coding agents.

## Rules

- Work only inside the standalone `Tailer/` repository.
- Update task status when starting or finishing work.
- Do not silently change scope; add a note under the task instead.
- Prefer completing one vertical slice before starting a new subsystem.

## Status Key

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked

## Active Tasks

### 1. Admin Write Actions Integration

- Status: `[ ]`
- Owner: `programmatic-agent`
- Goal: complete the admin-side write path against the existing backend API.

Scope:
- Connect the user creation form in `frontend/app/admin/users/page.tsx` to `POST /admin/users`
- Connect the key creation form in `frontend/app/admin/keys/page.tsx` to `POST /admin/keys`
- Connect key revoke actions in `frontend/app/admin/keys/page.tsx` to `DELETE /admin/keys/{key_id}`
- Refresh dashboard, users, and keys state after successful mutations
- Handle loading, success, and failure states clearly in the UI
- Do not start rotate/edit/delete features that the backend does not support yet

Acceptance:
- Admin can create a user from the UI.
- Admin can create a Sub-API key from the UI.
- Admin can revoke a key from the UI.
- The admin dashboard reflects those changes after refresh or local state update.
- `npm run build` still passes.

### 2. Repository Hygiene

- Status: `[ ]`
- Owner: `admin-agent`
- Goal: clean repo structure and keep the workspace stable for multi-agent work.

Scope:
- Decide whether `backend/venv/` stays in repo tree or is removed from tracked workspace use.
- Create `docs/` when documentation starts splitting out of `README.md`.
- Keep root planning and monitoring files current.

Acceptance:
- Repo structure matches intended long-term layout more closely.
- No confusion about active root or active plans.

### 3. Backend Persistence Foundation

- Status: `[ ]`
- Owner: `backend-agent`
- Goal: prepare the backend for moving off in-memory mock data.

Scope:
- Introduce a real backend project structure for persistence work
- Add database connection scaffolding
- Add Alembic setup
- Define initial database models for users, projects, sub keys, and usage events
- Do not remove the current mock flow until the replacement path is ready

Acceptance:
- Backend has a clear persistence foundation.
- Migration tooling exists.
- Current app still runs locally.

## Blocked Tasks

### 4. Private Remote Wiring

- Status: `[!]`
- Owner: `admin-agent`
- Blocker: missing private repo URL for `origin`.

Needed:
- GitHub or GitLab repo URL for the standalone `Tailer` repository.

## Completed Tasks

### Baseline Stabilization

- Status: `[x]`
- Frontend dependency drift fixed.
- Backend bearer-header handling fixed.
- Standalone project root established.
- Implementation plan copied into standalone repo.

### Frontend Read Integration

- Status: `[x]`
- Admin dashboard, users page, keys page, and user dashboard read from the backend API.
- Shared frontend API client exists in `frontend/lib/api.ts`.

### Local Dev Infrastructure

- Status: `[x]`
- Root `.env.example` exists.
- `docker-compose.yml` exists.
- Backend Dockerfile exists.
- Frontend Dockerfile exists.
