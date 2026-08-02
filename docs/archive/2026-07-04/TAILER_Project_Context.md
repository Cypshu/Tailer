# TAILER Project Context

> Archived agent context from 2026-07-04. It has been replaced by the root AGENTS.md and task board.
>
> Current checkpoint (2026-08-02): Iteration 1 persistence is complete and Iteration 2 implementation is complete; a disposable live OpenAI success smoke remains pending. See the root [task board](../../../tasks.md).

This file is the compact context-loading entrypoint for TAILER.

Use it before reading source code in depth. It is intended to give coding agents enough representative project context to work accurately without loading every file first.

## 1. Canonical Project Boundary

- Active project root: `C:\Users\Cypsa\Desktop\Hackathon\Tailer`
- Treat `Tailer/` as the only active application repository.
- Do not treat the outer `hackathon-prim/` repository as the TAILER codebase unless the user explicitly changes that decision.
- Repository type: standalone Git repo with `frontend/` and `backend/` in the root.

## 2. Project State At This Checkpoint

TAILER is a secure LLM API gateway and dashboard for controlled sub-API-key access to upstream LLM providers.

Current status is mixed:

- The repo has progressed beyond the original MVP baseline.
- Auth-related code, a login page, and a provider abstraction were added.
- Database/session, SQLAlchemy model, and Alembic migration scaffolding now exists.
- The active backend routes are still mock-data driven and not persistence-backed.
- The current worktree is dirty and appears to include concurrent agent work.
- Verified today:
  - frontend production build passes
  - backend starts cleanly in the current project venv
  - login, protected admin/user routes, and runtime smoke checks pass
  - login-page credentials now match the mock dataset
  - testing guide credentials and runtime examples match the mock dataset
  - form-field text color is fixed globally in the frontend

## 3. Primary Reference Documents

Read these when deeper planning context is needed:

- `TAILER_Project_Baseline.md`
- `TAILER_Program_Architecture.md`
- `TAILER_Project_Implementation_Plan.md`
- `TAILER_Surveillance_Role.md`
- `TAILER_Status_Checklist.md`
- `tasks.md`
- `SESSION_SUMMARY.md`

## 4. Current Architecture Snapshot

High-level shape:

- `frontend/`: Next.js 16 + React 19 dashboard UI
- `backend/`: FastAPI application exposing auth, admin, user, and runtime APIs
- `backend/app/database.py`, `backend/app/models_db.py`, `backend/alembic/`: persistence scaffold
- `docker-compose.yml`: local multi-service dev stack
- `.env.example`: root environment template

Intended request flow:

1. Login is handled through `POST /api/auth/login`.
2. The frontend stores the returned access token in `localStorage`.
3. `frontend/lib/api.ts` injects the bearer token into admin and user API calls.
4. Admin and user routes decode the JWT and derive the current identity.
5. Runtime requests still use Sub-API keys directly through `Authorization: Bearer ...`.
6. Backend data still comes from `backend/app/mock_data.py`.

## 5. Verified Findings From This Inspection

These were verified during this update pass:

- `npm run build` in `frontend/` passes.
- `npm run lint` in `frontend/` passes.
- The project venv now reports:
  - FastAPI `0.115.0`
  - Pydantic `2.11.7`
  - Pydantic Settings `2.6.0`
  - Uvicorn `0.30.0`
- Backend startup succeeds from the project venv.
- Live smoke checks passed for:
  - `GET /`
  - `GET /health`
  - `POST /api/auth/login`
  - `GET /admin/dashboard/stats` with admin token
  - `GET /admin/dashboard/stats` with user token returns `403`
  - `GET /admin/dashboard/stats` anonymously returns `401`
  - `GET /user/me` with token
  - `POST /v1/chat/completions` with valid Sub-API key
  - forbidden-model path returns `403`
- `frontend/app/globals.css` now enforces readable dark text on white input, textarea, and select controls.
- SQLAlchemy database/session setup, DB model definitions, Alembic config, and an initial migration are present.
- The persistence scaffold is not yet wired into active route data access.
- The repo now uses `TAILER_Project_Context.md` as the context filename; older references to `TAILER_Project _Context.md` are stale.
- The login UI now matches `backend/app/mock_data.py`, which defines:
  - `organizer@hackathon.dev`
  - `team_alpha@hackathon.dev`
  - `team_beta@hackathon.dev`
- `TESTING_GUIDE.md` now uses the current mock user and Sub-API key examples.

## 6. Backend Module Map

### `backend/main.py`

- Thin entrypoint that starts Uvicorn for the FastAPI app.

### `backend/app/main.py`

- Main FastAPI app module.
- Registers CORS.
- Mounts routers from:
  - `app.api.auth`
  - `app.api.admin`
  - `app.api.user`
  - `app.api.runtime`
- Owns the canonical `GET /` and `GET /health` endpoints.

### `backend/app/config.py`

- Pydantic settings definition.
- Uses `TAILER_` as the application settings prefix.
- Current fields include:
  - `app_name`
  - `debug`
  - `backend_url`
  - `frontend_url`
  - `database_url`
  - `redis_url`
  - `secret_key`
  - `jwt_secret_key`
  - `jwt_algorithm`
  - `jwt_expiration_minutes`
- Includes defensive parsing for common `TAILER_DEBUG` string values.

### `backend/app/database.py`

- SQLAlchemy engine and session bootstrap.
- Provides `get_db()` dependency for future route/service persistence work.
- Present but not yet used by the active auth/admin/user/runtime routes.

### `backend/app/models_db.py`

- SQLAlchemy persistence model scaffold for:
  - users
  - projects
  - sub_api_keys
  - usage_events
- Includes key-hash/prefix fields intended for safer Sub-API key storage.
- Present but not yet the active data model for runtime behavior.

### `backend/alembic/`

- Alembic configuration exists with an initial migration for the scaffolded core tables.
- Migration execution against the local database has not been verified in this pass.

### `backend/app/models.py`

- Pydantic contracts for users, keys, usage events, dashboard stats, and runtime request/response shapes.
- Still the active API schema layer, not the persistence layer.

### `backend/app/mock_data.py`

- Central in-memory dataset for users, projects, keys, and usage events.
- Current truth source for demo users and credentials.

### `backend/app/auth.py`

- JWT and password-hashing helper module.
- Provides:
  - password verification
  - password hashing
  - JWT creation
  - JWT decoding
- Auth flow is now wired through the live backend and passes basic route verification.

### `backend/app/api/auth.py`

- Auth router mounted at `/api/auth`.
- Provides `POST /api/auth/login`.
- Current MVP behavior uses mock users and compares the submitted password to the user's name.

### `backend/app/api/admin.py`

- Admin routes for dashboard stats, users, keys, and usage events.
- Intended to be bearer-token protected.
- Currently uses header-based bearer extraction compatible with the running backend environment.

### `backend/app/api/user.py`

- User self-service routes for `me`, keys, usage, and stats.
- Intended to be bearer-token protected.
- Currently uses header-based bearer extraction compatible with the running backend environment.

### `backend/app/providers.py`

- Provider abstraction boundary for LLM integrations.
- Defines a provider protocol and a `MockProvider`.
- Good foundation for future real provider integration.

### `backend/app/api/runtime.py`

- OpenAI-style runtime endpoint implementation.
- Main route: `POST /v1/chat/completions`
- Validates Sub-API keys against mock data and delegates generation to the provider abstraction.
- No longer owns a duplicate `/health` endpoint.

## 7. Frontend Module Map

### `frontend/lib/api.ts`

- Shared API client.
- Injects bearer auth from `localStorage`.
- The previous `headers` typing issue was fixed and the frontend production build now passes.

### `frontend/app/layout.tsx`

- Global app shell, fonts, metadata, and navigation wrapper.

### `frontend/app/globals.css`

- Global Tailwind import and app-level CSS variables.
- Now forces readable dark text, white backgrounds, dark carets, and stable placeholder color for input, textarea, and select controls.

### `frontend/components/Navigation.tsx`

- Route-aware navigation bar for admin and user areas.
- Includes a working logout action that clears `localStorage` and redirects to `/login`.

### `frontend/app/login/page.tsx`

- Login screen for demo auth flow.
- Demo credentials shown here now match `backend/app/mock_data.py`.

### `frontend/app/page.tsx`

- Landing page with login, admin, and user entry links.
- Marketing copy was updated beyond the original prototype wording.

### `frontend/app/admin/page.tsx`

- Admin dashboard overview page.
- Correctly derives per-user key counts from `owner_id`.
- Still contains explicit placeholder actions such as export and provider settings.

### `frontend/app/admin/users/page.tsx`

- User-management page.
- Can create users through the backend API.
- Edit and delete controls are still inert placeholders.

### `frontend/app/admin/keys/page.tsx`

- Key-management page.
- Can create keys, reveal keys, copy keys, and revoke keys.
- Key rotation is still explicitly marked as not implemented.

### `frontend/app/user/dashboard/page.tsx`

- User dashboard for stats, keys, and recent usage history.

## 8. Infrastructure and Environment

### `docker-compose.yml`

- Defines `postgres`, `redis`, `backend`, and `frontend`.
- Infrastructure exists even though the backend still uses mock data.
- Backend/frontend service settings use the `TAILER_` application env prefix where applicable.

### `.env.example`

- Documents project-scoped `TAILER_` application settings.
- Keeps external provider keys separate from TAILER app settings.

### `.gitignore`

- Python root `lib` and `lib64` ignores are anchored as `/lib/` and `/lib64/`.
- `frontend/lib/` is no longer hidden by the ignore rules; `frontend/lib/api.ts` is source code and should be tracked.

### `backend/alembic.ini`

- Alembic config file exists.
- Initial migration exists under `backend/alembic/versions/`.
- Migration execution has not been re-verified in this pass.

### `backend/requirements.txt`

- Includes FastAPI, Pydantic settings, SQLAlchemy, Alembic, and auth-related packages.
- `requirements.txt` now targets FastAPI `0.115.0`, Pydantic `2.11.7`, and Uvicorn `0.30.0`.
- The current project venv is now aligned with those versions.

## 9. Landed Features Versus Verified Health

Code-level features that have landed:

- auth helper module
- login route
- login page
- bearer token injection in frontend API client
- provider abstraction for runtime requests
- admin/user route protection intent
- global form-field color fix in `frontend/app/globals.css`
- database/session/model/Alembic persistence scaffold

Still true about the system:

- backend state is fully in-memory
- raw Sub-API key strings are still stored and returned
- persistence scaffold exists but active routes still do not use it
- migration execution against a live database has not been verified in this pass
- no real upstream provider integration exists
- no rate limiting or budget enforcement exists

Current verified health risks:

- backend is still entirely in-memory despite live route health
- placeholder admin actions still exist in the UI
- `.tailer-runs/` and loose helper scripts exist as local test artifacts

## 10. Highest-Priority Next Steps

1. Wire active routes through a service/repository layer instead of direct mock-data access.
2. Verify Alembic migrations against the local database and document the migration command.
3. Implement secure provider credential storage and hashed Sub-API key storage.
4. Add an executable automated test baseline for auth and runtime gateway paths.

## 11. Suggested Loading Order For Agents

If an agent needs minimal context only:

1. Read this file.
2. Read `TAILER_Surveillance_Role.md`.
3. Read `tasks.md`.

If an agent is doing backend work:

1. Read this file.
2. Read `backend/app/main.py`.
3. Read `backend/app/config.py`.
4. Read `backend/app/auth.py`.
5. Read `backend/app/api/auth.py`.
6. Read the relevant route module under `backend/app/api/`.

If an agent is doing frontend work:

1. Read this file.
2. Read `frontend/lib/api.ts`.
3. Read `frontend/app/login/page.tsx`.
4. Read the relevant page under `frontend/app/`.

If an agent is doing inspection or coordination work:

1. Read this file.
2. Read `TAILER_Surveillance_Role.md`.
3. Read `TAILER_Status_Checklist.md`.
4. Read `TAILER_Project_Implementation_Plan.md`.
5. Read `tasks.md`.

## 12. Short Project Summary

TAILER has moved past the original static MVP: auth scaffolding, provider abstraction, a login page, readable form styling, a working runtime path, and persistence scaffolding are in place. The repo is operational for local verification, but it is still short of MVP because active routes still use mock data and provider credential storage, model configuration, limits, pipelines, and automated tests are not implemented yet.
