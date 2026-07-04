# TAILER Agent Tasks

Use this file as the active task board for coding agents working in the standalone `Tailer/` repository.

## Rules

- Work only inside `Tailer/`.
- Update task status when starting or finishing work.
- Do not silently expand scope; add a short note under the task if scope changes.
- Prefer finishing the current milestone before starting a new subsystem.

## Status Key

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked

## Current State

- Phase 1 setup is complete.
- Frontend reads from the backend.
- Admin create/revoke actions exist.
- Backend is still fully in-memory and unauthenticated.
- User identity is still hardcoded in the backend.

## Active Tasks

### 1. Backend Persistence Foundation

- Status: `[~]`
- Owner: `backend-agent`
- Goal: replace the current in-memory-only backend foundation with real persistence scaffolding.
- Note: Database layer scaffolded. Ready for authentication integration.

Scope:
- Add database configuration to backend settings using project-scoped env names
- Add SQLAlchemy or SQLModel setup and session management
- Add Alembic
- Create initial persisted models for:
  - users
  - projects
  - sub_api_keys
  - usage_events
- Keep the current app runnable while the persistence layer is introduced
- Align docker/environment naming with the backend config as part of this work

Acceptance:
- Backend starts with database scaffolding in place
- Migrations can be created and applied
- Current API routes still run locally
- No hard dependency remains on raw global process env names

### 2. Authentication Skeleton

- Status: `[ ]`
- Owner: `backend-agent`
- Goal: remove the hardcoded user context and introduce a real auth base.

Scope:
- Add password hashing
- Add login endpoint
- Add auth token or session mechanism
- Replace `CURRENT_USER_ID = "user_1"` in `backend/app/api/user.py`
- Add admin/user route protection primitives
- Add a default admin bootstrap path for local development

Acceptance:
- Admin can authenticate
- `/user/me` is identity-driven instead of hardcoded
- Admin routes are protected from anonymous access

### 3. Admin Dashboard Correctness Pass

- Status: `[x]`
- Owner: `frontend-agent`
- Goal: fix current admin UI inconsistencies now that read/write integration exists.
- Completed: Fixed key counting logic, implemented copy-to-clipboard, added navigation to forms.

Scope:
- Fix incorrect user-to-key counting logic in `frontend/app/admin/page.tsx`
- Replace dead quick-action buttons with real navigation or remove them
- Make copy-to-clipboard actions work where shown
- Review any UI text that still implies placeholder behavior where the feature is live

Acceptance:
- Admin dashboard shows correct key counts per user
- No visible button is misleadingly inert without explanation
- Build still passes

## Blocked Tasks

### 4. Private Remote Wiring

- Status: `[!]`
- Owner: `admin-agent`
- Blocker: missing private repo URL for `origin`

Needed:
- GitHub or GitLab repository URL for the standalone `Tailer` repo

## Completed Tasks

### Repository Separation

- Status: `[x]`
- Standalone `Tailer/` repo created outside `hackathon-prim`
- Old nested copy removed

### Baseline Stabilization

- Status: `[x]`
- Frontend dependency drift fixed
- Backend bearer-header handling fixed
- Implementation plan copied into standalone repo

### Local Dev Infrastructure

- Status: `[x]`
- Root `.env.example` exists
- Root `docker-compose.yml` exists
- Backend Dockerfile exists
- Frontend Dockerfile exists

### Frontend Read Integration

- Status: `[x]`
- Admin dashboard reads from backend endpoints
- Admin users page reads from backend endpoints
- Admin keys page reads from backend endpoints
- User dashboard reads from backend endpoints
- Shared frontend API client exists

### Admin Write Actions Integration

- Status: `[x]`
- User creation form calls `POST /admin/users`
- Key creation form calls `POST /admin/keys`
- Key revoke action calls `DELETE /admin/keys/{key_id}`
