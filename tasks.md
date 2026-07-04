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

### 1. Frontend to Backend Integration

- Status: `[ ]`
- Owner: `programmatic-agent`
- Goal: replace local frontend mock-data usage with live backend API calls.

Scope:
- Remove dependency on `frontend/lib/mockData.ts` from:
  - `frontend/app/admin/page.tsx`
  - `frontend/app/admin/users/page.tsx`
  - `frontend/app/admin/keys/page.tsx`
  - `frontend/app/user/dashboard/page.tsx`
- Fetch from:
  - `GET /admin/dashboard/stats`
  - `GET /admin/users`
  - `GET /admin/keys`
  - `GET /admin/usage`
  - `GET /user/me`
  - `GET /user/keys`
  - `GET /user/usage`
  - `GET /user/stats`
- Add one frontend backend-base-url config point.

Acceptance:
- Admin pages render using backend data.
- User dashboard renders using backend data.
- `npm run build` still passes.

### 2. Local Dev Infrastructure

- Status: `[ ]`
- Owner: `infra-agent`
- Goal: complete remaining Phase 1 local environment setup.

Scope:
- Add root `.env.example`
- Add root `docker-compose.yml`
- Add backend Dockerfile
- Add frontend Dockerfile

Acceptance:
- Local stack can be started with one documented command.
- README matches actual startup flow.

### 3. Repository Hygiene

- Status: `[ ]`
- Owner: `admin-agent`
- Goal: clean repo structure and reduce environment-specific clutter.

Scope:
- Decide whether `backend/venv/` stays in repo tree or is removed from tracked workspace use.
- Create `docs/` when documentation starts splitting out of `README.md`.
- Keep root planning and monitoring files current.

Acceptance:
- Repo structure matches intended long-term layout more closely.
- No confusion about active root or active plans.

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
