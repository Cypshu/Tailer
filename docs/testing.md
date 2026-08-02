# TAILER Testing Guide

Last verified: 2026-08-02

## Current testing status

TAILER has an isolated backend regression suite under `backend/tests/`.

- `backend/requirements-dev.txt` declares compatible `pytest` and `httpx` versions and includes runtime requirements.
- FastAPI `TestClient` exercises the API without starting a live server.
- An autouse fixture restores users, projects, keys, usage events, dependency overrides, and provider state around every test.
- The Alembic test uses a fresh temporary SQLite database.
- The generated `.tailer-runs/` harness is local smoke tooling, not a tracked regression layer.
- The loose root runtime demo was removed; it is not pytest evidence.

## Verified commands

### Frontend

~~~bash
cd frontend
npm run lint
npm run build
~~~

Both passed on 2026-08-02.

### Backend syntax

~~~bash
cd backend
pip install -r requirements-dev.txt
python -m compileall -q app
python -m pytest -q
python -m pytest -q tests/test_migrations.py tests/test_runtime.py tests/test_admin.py tests/test_auth.py
~~~

Both pytest commands passed on 2026-08-02: 48 tests in normal order and 48 in reversed file order. They required no live backend, PostgreSQL, or Redis process. Remaining warnings come from the installed `python-jose` package's use of deprecated `datetime.utcnow()`.

### Infrastructure configuration

~~~bash
docker compose config --quiet
~~~

Configuration rendering passed. Full service startup was not verified because the Docker daemon was unavailable.

### Migration validation

~~~bash
cd backend
alembic heads
alembic upgrade head --sql
~~~

Head discovery and offline SQL generation passed. `tests/test_migrations.py` also passed this online sequence against a fresh temporary SQLite database:

1. Upgrade to `head` and assert the expected tables.
2. Downgrade to `base` and assert application tables are gone.
3. Upgrade to `head` again and assert the expected tables return.

An independent `alembic check` at head reported no new upgrade operations. A PostgreSQL round-trip remains unverified because the Docker daemon is unavailable and nothing is listening on local port 5432.

## Manual API smoke flow

Start the backend at http://localhost:8000 before running these checks.

### 1. Health

~~~bash
curl http://localhost:8000/health
~~~

Expected: HTTP 200 with `{"status":"healthy"}`.

### 2. Admin login

~~~bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"organizer@hackathon.dev","password":"Hackathon Organizer"}'
~~~

Expected:

- HTTP 200
- `token_type` is `bearer`
- `user_id` is `user_3`
- `role` is `admin`

Save `access_token` as `ADMIN_TOKEN`.

### 3. Protected admin access

~~~bash
curl http://localhost:8000/admin/dashboard/stats \
  -H "Authorization: Bearer ADMIN_TOKEN"
~~~

Expected: HTTP 200.

Without a token, expect 401. With a normal user token, expect 403.

### 4. User login and identity

~~~bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"team_alpha@hackathon.dev","password":"Team Alpha"}'
~~~

Save the token as `USER_TOKEN`, then:

~~~bash
curl http://localhost:8000/user/me \
  -H "Authorization: Bearer USER_TOKEN"
~~~

Expected: HTTP 200 with `id` equal to `user_1`.

### 5. Valid runtime request

~~~bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer tailer_sub_xxxxxxxxxxxxx1" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Smoke test"}],
    "max_tokens": 20
  }'
~~~

Expected: HTTP 200 with an OpenAI-style response from `MockProvider` and a usage object.

### 6. Runtime rejection cases

| Case | Expected |
| --- | --- |
| Missing or invalid Sub-API key | 401 |
| Revoked Sub-API key | 401 |
| Expired Sub-API key | 401 |
| Model absent from the key allow list | 403 |
| Valid allowed model | 200 |

The runtime enforces active status, expiration, model permission, and request-schema bounds before provider invocation. It does not yet enforce rate limits, request-count/token budgets, or a per-key max-token policy.

## Browser flow

1. Open http://localhost:3000/login.
2. Log in with an exact demo identity.
3. Confirm admin redirects to `/admin` and user redirects to `/user/dashboard`.
4. Confirm the dashboard loads protected data.
5. Log out and confirm local auth state is cleared.

Raw Sub-API keys are visible and copyable in the current UI. This is a known security gap, not the target behavior.

## Swagger limitation

The backend routes parse bearer tokens through ordinary header dependencies. The generated OpenAPI schema does not currently define a bearer security scheme, so Swagger UI does not provide a reliable global Authorize flow for these routes. Use curl, the frontend, or the automated suite.

## Automated coverage

The current suite covers:

- valid and invalid login
- anonymous and role-denied admin access
- authenticated user identity and key scoping
- valid, invalid, revoked, expired, and model-denied runtime keys
- request validation boundaries
- usage event creation after success
- no success event after pre-provider rejection
- isolated reset of global mock state
- configured JWT secret, algorithm, and token lifetime
- normalized email, duplicate conflict, owner existence, future expiry, and positive key limits
- provider option forwarding and measured latency
- rejection of invalid provider usage/cost before ledger mutation
- environment-driven Alembic migration round-trip

Acceptance is `cd backend && python -m pytest` passing without a live backend, PostgreSQL, or Redis process; that acceptance passed on 2026-08-02.
