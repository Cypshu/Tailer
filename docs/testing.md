# TAILER Testing Guide

Last verified: 2026-08-24

## Current testing status

TAILER has a 386-case backend regression suite under `backend/tests/`.

- `backend/requirements-dev.txt` includes compatible `pytest` and `httpx` versions plus runtime requirements.
- FastAPI `TestClient` exercises the API without starting a live server.
- Every client/API contract runs against both a fresh `MemoryUnitOfWorkFactory` store and a fresh Alembic-migrated SQLite database through `SqlAlchemyUnitOfWorkFactory`.
- Dependency overrides, provider substitution, and credential-keyring settings
  are isolated around tests.
- Repository tests cover idempotent/pepper-aware seeding, commit/rollback,
  detached memory records, serialized memory transactions, HMAC lookup,
  hash-at-rest, SQL durability after reopening the engine, safe expected-write
  failure mapping, and rollback after flushed usage writes.
- Credential tests cover AES-256-GCM round-trips, unique nonces, authenticated
  associated-data binding, tamper rejection, missing-version failure, safe
  hints, and version rotation.
- Provider tests exercise OpenAI Chat Completions and native Gemini Interactions
  against mocked upstreams, strict response parsing, thought-token accounting,
  configured alias/pricing resolution, metadata-only admin responses, sanitized
  error mapping with explicit execution certainty, secret-safe logs, and
  certainty-appropriate durable provider-failure outcomes with stable
  `error_code` values. Smoke-orchestration tests cover loopback pinning,
  timeout validation, full-stack health, exact cleanup, secret exclusion from
  Compose, and cleanup retry.
- The standalone migration test reaches Alembic revision `0004`, inspects the
  request-attempt constraints, foreign keys, indexes, and historical null usage
  links, checks schema drift, and performs upgrade/downgrade/re-upgrade.
- `.tailer-runs/` is generated local smoke output, not the tracked regression layer.

The automated suite needs no live backend, PostgreSQL, or Redis process. SQLite supplies the isolated SQL implementation; PostgreSQL and Compose are verified separately.

## Verified commands

### Frontend

~~~bash
cd frontend
npm run lint
npm run build
~~~

Both passed on 2026-08-24.

### Backend

~~~bash
cd backend
pip install -r requirements-dev.txt
python -m compileall -q app tests
python -m pytest -q
python -m pytest -q tests/test_request_attempts.py tests/test_runtime.py tests/test_repositories.py tests/test_migrations.py tests/test_providers.py tests/test_gemini_provider.py tests/test_provider_api_integration.py
~~~

On 2026-08-24, compilation passed, the focused I0003 runtime/repository/
migration/provider matrix passed 267 tests, and the full suite passed 386 tests
in normal order. The preceding I0002 baseline passed 259 tests on the same
date. The earlier 229-case suite passed in normal and reversed file order on
2026-08-02, using `cryptography` 49.0.0.

The remaining warnings are understood third-party/dialect warnings:

- `python-jose` internally uses deprecated `datetime.utcnow()`.
- SQLite cannot reflect the expression-based unique lower-email index, so SQLAlchemy/Alembic warn while comparing it. The migration and drift assertions still pass.

### Lifecycle and infrastructure

~~~bash
docker compose config --quiet
./tailer.sh config
./tailer.sh start
./tailer.sh status
./tailer.sh gemini-smoke  # explicit paid/external verification only
~~~

On Windows, use `.\tailer.cmd config`, `.\tailer.cmd start`,
`.\tailer.cmd status`, and the explicit `.\tailer.cmd gemini-smoke` verification
command.

At the Iteration 1 checkpoint, Docker Engine 29.6.1 and Compose 5.2.0 passed an
isolated full build/start. PostgreSQL, Redis, backend, and frontend all became
healthy; backend/frontend HTTP checks and an admin login passed. The disposable
verification stack was removed without touching existing TAILER volumes.

The canonical Windows controller then started and restarted the real development
stack. A live acceptance probe created one user concurrently twice (one 200 and
one 409), created and used a show-once key, revoked it, and restarted the full
stack. The user, revocation, safe key prefix, and usage event all survived.
Direct PostgreSQL inspection confirmed Alembic `0002` and no raw key at rest.
The exact probe rows were removed, the final stack remained healthy, and fresh
backend logs contained no probe bearer/identity or error markers.

The Windows controller also passed help, configuration, status, service
filtering, interactive exit, error/exit-code, and outside-working-directory
checks. The Bash controller passed syntax and help checks. Current Compose and
controller configuration validation also passes. `docker compose config
--quiet` passed again on 2026-08-24.

For Iteration 2, a clean backend image built with `cryptography` 49.0.0 and a
disposable PostgreSQL 16 database completed upgrade, `alembic check`, downgrade,
and re-upgrade at `0003`. A live configured credential/model route used
AES-256-GCM persistence and the real OpenAI adapter against a deliberately
non-routable HTTPS upstream. It returned only sanitized
`provider_unavailable`, durably stored the stable `error_code`, survived a
backend restart, and exposed neither raw secret nor ciphertext through APIs,
database inspection, or logs. Exact probe rows and the disposable database were
removed.

A final canonical `tailer.cmd restart` left PostgreSQL, Redis, backend, and
frontend healthy, with the database at `0003` and a passing deterministic mock
completion. The loopback-only Gemini pipeline subsequently discovered Gemini
3.6 Flash, completed through TAILER before and after backend restart, verified
two durable success events with nonzero configured pricing, checked API,
database, and logs for secrets, removed exact probe rows, and restored all four
services. The final backend container intentionally has an empty credential
keyring. Iteration 2 is complete.

The systemd paths, ordering, and lifecycle semantics were reviewed, but the unit
was not started or checked with `systemd-analyze` because the available WSL1
host has no systemd/cgroups; verify it once on the target Linux host.

### Migration validation

~~~bash
cd backend
alembic heads
alembic upgrade head --sql
~~~

Verified migration behavior:

1. A temporary SQLite database upgrades to head `0003` and contains the expected tables, including `provider_credentials` and `model_configs`.
2. `alembic check` reports no new upgrade operations.
3. Downgrade to `base` removes the application tables.
4. Re-upgrade reaches `0003` again.
5. A clean disposable PostgreSQL 16 database completes upgrade, `alembic check`, downgrade, and re-upgrade at `0003`.
6. The deterministic SQL seed can run twice without adding duplicates.
7. Two seed processes started simultaneously against a fresh PostgreSQL database
   both succeed and converge to `3|1|3|4` records; the probe database was removed.

## Manual API smoke flow

Start the stack and wait for health before these checks.

### 1. Health

~~~bash
curl http://localhost:8000/health
~~~

Expected: HTTP 200 with `{"status":"healthy"}`.

Then verify repository readiness:

~~~bash
curl http://localhost:8000/ready
~~~

Expected: HTTP 200 with `{"status":"ready"}`. A configured repository failure returns 503 while `/health` remains a liveness-only check.

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

Expected: HTTP 200. Without a token, expect 401. With a normal user token, expect 403.

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

The following bearer is a deterministic development fixture. Persisted rows contain only its HMAC digest and display prefix.

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

Expected: HTTP 200 with an OpenAI-style response from `MockProvider`, a usage
object, and a `Tailer-Attempt-Id` response header. A durable attempt and its
linked usage row are committed before the success response returns.

For duplicate protection, add a unique, stable header value such as
`Idempotency-Key: smoke-<client-generated-id>`. The value is optional,
case-sensitive, and limited to 1–255 visible ASCII characters without
whitespace. It is HMACed rather than stored. Omitting it preserves the
backwards-compatible behavior in which each request is a fresh attempt.

If the provider returns successfully but an expected local usage flush or
commit failure prevents finalization, the response is HTTP 503 with exactly
`{"detail":"Usage finalization is unavailable"}`. The same detail is used if
a provider-failure audit event cannot be finalized. Focused tests prove one
provider call, one cost calculation after provider success, no automatic
provider retry, and no committed usage row through either adapter for the
injected failed-flush/pre-commit paths. The endpoint has no cross-request
automatic recovery contract. With a retained `Idempotency-Key`, the failed
attempt remains fenced and a client retry does not call the provider again;
without the header, a retry is a fresh request.

For the same authenticated Sub-API key, canonical effective request, operation,
and retained `Idempotency-Key`, the tested contract is at most one provider
dispatch and at most one linked usage event. Successful content is not stored,
so a matching completed duplicate returns HTTP 409 with
`completed_result_not_replayable`. A different payload under the same retained
key returns HTTP 409 with `idempotency_key_reused`; an in-progress duplicate
returns HTTP 409 with `request_in_progress`. A definite provider non-execution
replays only its sanitized error envelope, while an uncertain provider outcome
returns the fixed fenced HTTP 503 contract on later duplicates. Resolved keyed
identities use the configured retention window (30 days by default); uncertain
identities do not expire automatically. The API does not promise exactly-once
provider execution or charging, output replay, automatic recovery, or liveness.

### 6. Runtime rejection cases

| Case | Expected |
| --- | --- |
| Missing or invalid Sub-API key | 401 |
| Revoked Sub-API key | 401 |
| Expired Sub-API key | 401 |
| Model absent from the key allow list | 403 |
| Requested `max_tokens` exceeds the key ceiling | 403 |
| Invalid `Idempotency-Key` | 400, no attempt or provider call |
| Valid allowed model | 200 |

The runtime checks active status, expiration, project state, model permission,
per-key output-token ceiling, and request-schema bounds before provider-route
resolution. It does not yet enforce rate limits or aggregate request-count/token
budgets.

### 7. Provider-management contract

Authenticated admins can call:

- `GET|POST /admin/provider-credentials`
- `DELETE /admin/provider-credentials/{credential_id}` to revoke
- `GET|POST /admin/model-configs`
- `DELETE /admin/model-configs/{config_id}` to disable

Credential create accepts a plaintext `credential` once. Every response is
metadata-only: `credential` and stored `ciphertext` are never response fields.
A model configuration maps its public alias to the credential's provider,
concrete provider model, and non-negative input/output EUR prices per million
tokens. Revoking a credential also disables its enabled model configurations.

The keyring described in [setup](setup.md#provider-credential-encryption) must be
configured before credential creation. Without it, creation fails closed with
HTTP 503 and does not add a row.

### 8. Opt-in live Gemini pipeline

Run this only with exclusive use of a disposable development stack. It performs
model discovery and two paid/external completions, temporarily recreates the
backend/frontend with a generated credential-encryption key, and restarts the
backend between calls. The runner is pinned to `http://127.0.0.1:8000` and
refuses transient Compose overrides, an existing credential keyring, or a
provider/model configuration.

Put one disposable key on a single line in the ignored root `.gemini_api` file.
On Unix, require private permissions. Never print or copy the value into Docker,
an environment file, or a command argument:

~~~bash
chmod 600 .gemini_api
./tailer.sh gemini-smoke
~~~

On Windows:

~~~powershell
.\tailer.cmd gemini-smoke
~~~

Success means all nine stages pass: dynamic Flash-model discovery, clean
exclusive baseline, four-service health with an ephemeral keyring, encrypted
metadata-only credential storage, show-once Sub-API key creation, a live
user-visible completion, a second user-visible completion after backend restart,
durable token/cost and redaction checks, captured-ID plus project/provider-
scoped marker cleanup, cleanup retry verification, and complete canonical-stack
restoration. The upstream key never enters Docker
environment variables/build contexts/arguments, and the final backend has an
empty keyring. Delete `.gemini_api` and rotate/revoke the disposable key after
testing.

### 9. Optional OpenAI-specific smoke

This is optional provider-specific coverage; Gemini already satisfies Iteration
2's one-real-provider gate. Run it only against a disposable development
stack/database and with a disposable OpenAI API key. The automated suite uses a
mocked upstream for OpenAI success behavior.

The Bash outline below keeps the provider secret out of command literals and
files. It reads the secret without echo, sends JSON on stdin, unsets the
plaintext immediately after credential creation, and uses a one-off Sub-API key
and alias. Set the provider model and current EUR pricing values appropriate to
the disposable OpenAI account before running it.

~~~bash
export TAILER_OPENAI_MODEL='<operator-selected Chat Completions model>'
export TAILER_OPENAI_INPUT_RATE_EUR='<input EUR per million tokens>'
export TAILER_OPENAI_OUTPUT_RATE_EUR='<output EUR per million tokens>'
export TAILER_SMOKE_SUFFIX="$(date +%s)"
export TAILER_PUBLIC_MODEL="tailer-openai-smoke-${TAILER_SMOKE_SUFFIX}"

export TAILER_ADMIN_TOKEN="$(
  curl -fsS -X POST http://localhost:8000/api/auth/login \
    -H 'Content-Type: application/json' \
    --data-binary '{"email":"organizer@hackathon.dev","password":"Hackathon Organizer"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
)"

read -rsp 'Disposable OpenAI API key: ' TAILER_OPENAI_API_KEY
echo
export TAILER_OPENAI_API_KEY
export TAILER_CREDENTIAL_ID="$(
  python - <<'PY' | curl -fsS -X POST http://localhost:8000/admin/provider-credentials \
    -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' --data-binary @- \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])'
import json, os
print(json.dumps({
    "provider": "openai",
    "name": f"disposable-openai-smoke-{os.environ['TAILER_SMOKE_SUFFIX']}",
    "credential": os.environ["TAILER_OPENAI_API_KEY"],
}))
PY
)"
unset TAILER_OPENAI_API_KEY

export TAILER_MODEL_CONFIG_ID="$(
  python - <<'PY' | curl -fsS -X POST http://localhost:8000/admin/model-configs \
    -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' --data-binary @- \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])'
import json, os
print(json.dumps({
    "public_model": os.environ["TAILER_PUBLIC_MODEL"],
    "provider_model": os.environ["TAILER_OPENAI_MODEL"],
    "credential_id": os.environ["TAILER_CREDENTIAL_ID"],
    "input_cost_per_million_eur": os.environ["TAILER_OPENAI_INPUT_RATE_EUR"],
    "output_cost_per_million_eur": os.environ["TAILER_OPENAI_OUTPUT_RATE_EUR"],
}))
PY
)"

read -r TAILER_SMOKE_KEY_ID TAILER_SMOKE_SUB_KEY < <(
  python - <<'PY' | curl -fsS -X POST http://localhost:8000/admin/keys \
    -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}" \
    -H 'Content-Type: application/json' --data-binary @- \
  | python -c 'import json,sys; p=json.load(sys.stdin); print(p["id"], p["key"])'
from datetime import datetime, timedelta, timezone
import json, os
print(json.dumps({
    "name": f"openai-smoke-{os.environ['TAILER_SMOKE_SUFFIX']}",
    "owner_user_id": "user_1",
    "allowed_models": [os.environ["TAILER_PUBLIC_MODEL"]],
    "daily_request_limit": 10,
    "monthly_token_limit": 10000,
    "monthly_budget_eur": 10,
    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
}))
PY
)
export TAILER_SMOKE_KEY_ID TAILER_SMOKE_SUB_KEY

python - <<'PY' | curl -sS -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer ${TAILER_SMOKE_SUB_KEY}" \
  -H 'Content-Type: application/json' --data-binary @- \
  -w '\nHTTP %{http_code}\n'
import json, os
print(json.dumps({
    "model": os.environ["TAILER_PUBLIC_MODEL"],
    "messages": [{"role": "user", "content": "Reply with OK."}],
    "max_tokens": 20,
    "temperature": 0.7,
}))
PY

curl -fsS "http://localhost:8000/admin/usage?key_id=${TAILER_SMOKE_KEY_ID}" \
  -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}"

curl -fsS -X DELETE "http://localhost:8000/admin/model-configs/${TAILER_MODEL_CONFIG_ID}" \
  -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}"
curl -fsS -X DELETE "http://localhost:8000/admin/provider-credentials/${TAILER_CREDENTIAL_ID}" \
  -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}"
curl -fsS -X DELETE "http://localhost:8000/admin/keys/${TAILER_SMOKE_KEY_ID}" \
  -H "Authorization: Bearer ${TAILER_ADMIN_TOKEN}"
unset TAILER_ADMIN_TOKEN TAILER_CREDENTIAL_ID TAILER_MODEL_CONFIG_ID
unset TAILER_SMOKE_KEY_ID TAILER_SMOKE_SUB_KEY TAILER_SMOKE_SUFFIX TAILER_PUBLIC_MODEL
unset TAILER_OPENAI_MODEL TAILER_OPENAI_INPUT_RATE_EUR TAILER_OPENAI_OUTPUT_RATE_EUR
~~~

Success requires HTTP 200 from the runtime call, a normalized completion, and a
durable `success` usage event containing the public alias, concrete provider
model, reported tokens, and configured estimated cost. A provider error must
instead return only its stable sanitized error object and add a zero-token
`failed` or `rate_limited` event with the matching `error_code`. Inspect logs to
confirm neither the provider secret nor Sub-API bearer appears.

## Browser flow

1. Open http://localhost:3000/login.
2. Log in with an exact demo identity.
3. Confirm admin redirects to `/admin` and a user redirects to `/user/dashboard`.
4. As an admin, create a key and confirm its raw bearer appears in the one-time creation panel.
5. Copy or save the raw bearer, dismiss the panel, and confirm list/detail views show only `key_prefix`.
6. Restart the backend and confirm persisted users, keys, revocations, and usage remain.
7. Log out and confirm local dashboard auth state is cleared.

## Swagger limitation

The backend routes parse bearer tokens through ordinary header dependencies. The generated OpenAPI schema does not currently define a bearer security scheme, so Swagger UI does not provide a reliable global Authorize flow. Use curl, the frontend, or the automated suite.

## Automated coverage

The current suite covers:

- valid and invalid login, configured JWT settings, and role boundaries
- separate liveness and repository-readiness behavior
- authenticated identity, key scoping, and safe key representations
- validated admin/user usage pagination bounds
- normalized email, duplicate conflict, owner existence, future expiry, and positive key limits
- creation-only raw keys, HMAC lookup, and absence of raw secrets from persisted hashes
- valid, invalid, revoked, expired, and model-denied runtime keys
- request validation before provider invocation
- exact-boundary and over-limit per-key output-token policy, including zero
  provider-route, provider-call, and cost-calculation work for denials
- provider option forwarding, measured latency, and normalized successful usage
- rejection of invalid provider usage/cost before ledger mutation
- optional metadata-only request identity, exact duplicate/error envelopes, and
  `Tailer-Attempt-Id` propagation without changing the success body
- deterministic two-client keyed races through both adapters, including real
  SQL uniqueness, with one claim, one provider call, one cost calculation, and
  one linked usage event
- claim and terminal commit-acknowledgement ambiguity, dispatch-token ownership,
  double-finalization fencing, and fixed secret-safe availability responses
- 30-day resolved identity retirement with preserved historical accounting
  anchors, plus indefinite fencing for unresolved attempts
- raw bearer/idempotency keys, canonical requests, prompts, outputs, provider
  payloads, and persistence-driver sentinels excluded from attempt/usage rows,
  handled duplicate/failure responses, and captured logs
- synthetic Mock/Gemini response IDs derived from transient content excluded
  from durable attempt metadata while allowlisted upstream IDs remain usable
- provider-success/local-finalization failure with exactly one provider call,
  one cost calculation, fixed secret-safe HTTP 503 detail, no automatic retry,
  and no committed usage row through either adapter
- matching finalization-failure behavior for provider-failure audit writes,
  plus SQL flush/commit rollback and programming-error pass-through
- versioned AES-256-GCM encryption, associated-data binding, redaction, tamper
  detection, missing-key failure, and re-encryption to an active key version
- provider-credential and model-configuration repository/API contracts without
  plaintext or ciphertext response fields
- model-alias/provider-model routing and configured per-million-token EUR pricing
- OpenAI Chat Completions request/response translation against a mocked upstream
- native Gemini Interactions translation, `store=false`, system/user/model
  history, thought-token accounting, incomplete thought-only responses, and
  deterministic IDs for unstored interactions
- sanitized timeout, availability, authentication, permission, not-found,
  rate-limit, request-rejection, and malformed-response errors
- durable zero-token provider-failure events with stable `error_code` values
  when local audit finalization succeeds
- identical API behavior through in-memory and SQLAlchemy adapters
- unit-of-work commit/rollback, detached memory reads, and serialized memory transactions
- two-run seed idempotency, pepper-change preservation, and SQL durability after engine reopen
- environment-driven Alembic migration round-trip through `0004`, legacy
  latency backfill, request-attempt schema inspection, and drift detection

## Known unimplemented test areas

- No frontend component or browser end-to-end suite exists.
- No provider-credential or model-configuration management frontend exists.
- OpenAI-specific live success remains optional additional adapter coverage;
  native Gemini supplied the completed provider-neutral live gate.
- Redis/concurrency quota tests await policy enforcement.
- Provider-failure audit tests exist; pre-provider blocked-event audit tests
  await that durable event type.
- Automated attempt recovery/reconciliation, response replay, and a request
  status API are intentionally absent from the current contract.
- Production backup, restore, HTTPS, and secret-rotation drills are not defined.
