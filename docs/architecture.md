# TAILER Architecture

This document separates current implementation from target architecture. For delivery status, use `tasks.md` and the implementation plan.

## Current implementation

~~~text
Next.js browser UI
  -> JWT-authenticated /admin and /user routes
  -> FastAPI
  -> mutable mock users, keys, projects, and usage lists

External client
  -> raw demo Sub-API bearer key
  -> POST /v1/chat/completions
  -> validated request, active/expiry, and allowed-model checks
  -> MockProvider
  -> in-memory success usage append
~~~

Persistence scaffolding exists but is inactive:

- `backend/app/database.py`
- `backend/app/models_db.py`
- `backend/alembic/`
- `backend/alembic.ini`

Every active route still imports mock state directly.

## Target MVP architecture

~~~text
Admin/User browser
  -> dashboard authentication and RBAC
  -> admin/user application services

External client
  -> Sub-API key verification
  -> policy service
  -> model configuration
  -> provider adapter
  -> upstream LLM

Application services
  -> repositories
  -> PostgreSQL

Policy service
  -> Redis counters
  -> PostgreSQL durable limits and usage

All runtime outcomes
  -> durable usage/audit event
~~~

## Stable API namespaces

The MVP preserves the live route families:

### Authentication

- `POST /api/auth/login`
- Future refresh/logout behavior must be added deliberately; placeholders are not contracts.

### Admin

- `GET /admin/dashboard/stats`
- `GET|POST /admin/users`
- `GET /admin/users/{user_id}`
- `GET|POST /admin/keys`
- `GET|DELETE /admin/keys/{key_id}`
- `GET /admin/usage`

New project, provider, and model endpoints should remain under `/admin` for this API generation.

### User

- `GET /user/me`
- `GET /user/keys`
- `GET /user/keys/{key_id}`
- `GET /user/usage`
- `GET /user/stats`

### Runtime

- `POST /v1/chat/completions`

A future incompatible API must use an explicit version rather than silently changing these responses.

## Authentication boundaries

Dashboard tokens and runtime keys have different purposes:

- Dashboard JWT: identifies a human admin or user for management APIs.
- Sub-API key: identifies a client application for runtime requests.

The two credentials must not be interchangeable.

Target dashboard auth:

- hashed user passwords;
- configured JWT secret, algorithm, and expiration;
- stable `sub` claim;
- role lookup from persisted user state;
- optional refresh/session work after the baseline is secure.

Target runtime auth:

- random high-entropy raw key returned once;
- stored keyed hash and display prefix;
- constant-time verification;
- active, revoked, and expiration checks;
- project and owner association.

## Runtime request flow

~~~text
1. Parse Authorization bearer key.
2. Verify hashed key and load owner/project.
3. Check status and expiry.
4. Validate payload and requested model alias.
5. Reserve/check rate and budget policy.
6. Resolve provider credential and provider model.
7. Invoke the provider adapter.
8. Normalize response and usage.
9. Persist success or failure usage.
10. Commit counters and return a stable response.
~~~

Steps 1–6 must complete before an upstream call.

## Service and repository boundaries

Routes should coordinate HTTP concerns only. Introduce small services/repositories for:

- users and dashboard identity;
- projects;
- Sub-API keys;
- provider credentials;
- model configurations;
- usage events;
- policy decisions.

Migration sequence:

1. Characterize current API behavior with tests.
2. Put mock lists behind an in-memory repository.
3. Inject repositories into routes.
4. Add SQLAlchemy repositories.
5. Cut over one vertical path at a time.
6. Retain the in-memory adapter for isolated tests only.

## Canonical persistence model

### users

- `id`
- `email`, unique
- `name`
- `password_hash`
- `role`
- timestamps

### projects

- `id`
- `name`
- `description`
- `status`
- timestamps

The first MVP may seed one default project. Organizations are deferred.

### sub_api_keys

- `id`
- `project_id`
- `owner_id`
- `name`
- `key_hash`, unique
- `key_prefix`
- `status`
- `allowed_models`
- request/token/cost limits
- `max_tokens_per_request`
- `expires_at`
- timestamps

The normal API representation never contains the raw key. A dedicated creation response contains it once.

### usage_events

- `id` or request ID
- `project_id`
- `sub_api_key_id`
- `user_id`
- `provider`
- public and provider model names
- input, output, and total tokens
- estimated cost and currency
- latency
- status and stable error code
- `created_at`

Use `created_at` internally. The API may expose a compatibility `timestamp` field through schema mapping.

### provider_credentials

Add in the secure-provider iteration:

- `id`
- `project_id`
- provider and display name
- encrypted credential ciphertext and key version
- status
- timestamps

Never return ciphertext or raw credential values.

### model_configs

Add with the first real provider:

- `id`
- `project_id`
- public alias
- provider and provider model
- credential reference
- enabled state
- input/output pricing metadata
- timestamps

## API-to-ORM decisions required before persistence

The current API and ORM do not align mechanically. The persistence design task must resolve:

| Current API | Current ORM | Required decision |
| --- | --- | --- |
| Key includes raw `key` | `key_hash` and `key_prefix` | create-only secret response plus safe read schema |
| Key creation has no project | `project_id` required | explicit or seeded default project |
| Usage uses `timestamp` | `created_at` | compatibility schema mapping |
| Usage uses `sub_key_id` | `sub_api_key_id` | one internal name and mapped output |
| Usage omits provider/project | both required | populate from resolved runtime context |

Do not start route cutover until these mappings are tested and documented.

## Provider boundary

`backend/app/providers.py` is the correct abstraction point.

A provider adapter must:

- accept normalized messages and generation options;
- use only backend-held credentials;
- return normalized choices and token usage;
- expose typed provider failures;
- support test substitution;
- avoid logging secrets or prompt content by default.

Implement one real provider first. Multi-provider routing follows only after the first adapter is reliable.

## Policy architecture

Policy decisions should return a structured result:

~~~json
{
  "allowed": false,
  "code": "monthly_budget_exceeded",
  "message": "This key has reached its monthly budget."
}
~~~

Initial policy order:

1. key status and expiration
2. model permission
3. max tokens per request
4. request-rate limits
5. token limits
6. cost limits

Redis may hold fast counters, but PostgreSQL remains the durable source for configuration and usage.

## Usage and privacy

Record metadata for successful, failed, and blocked requests. Do not store full prompts or outputs by default.

Usage writes must be:

- durable across restart;
- attributable to project, user, and key;
- explicit about estimated versus provider-reported cost;
- safe under concurrent requests;
- auditable enough for later billing preparation.

## Frontend architecture

The frontend uses the Next.js App Router:

- `/login`
- `/admin`
- `/admin/users`
- `/admin/keys`
- `/user/dashboard`

`frontend/lib/api.ts` is the shared dashboard API client. It injects the dashboard JWT from browser storage.

The runtime endpoint should not automatically receive that JWT. Runtime examples use a Sub-API key explicitly.

Target UI work follows backend contracts:

- show raw key once after creation;
- show prefix and metadata on later reads;
- expose allowed models and real enforcement state;
- label unavailable actions as unavailable;
- avoid claiming provider, persistence, or policy features before they exist.

## Deployment shape

Local development uses Compose services for:

- PostgreSQL
- Redis
- FastAPI backend
- Next.js frontend

Production additionally requires:

- HTTPS termination;
- managed secrets;
- migration execution;
- backups;
- structured logs and error monitoring;
- health/readiness checks;
- restricted database and Redis networking.

## Deferred architecture

The pipeline engine, multi-organization tenancy, billing, advanced RAG, and agent orchestration are intentionally outside the core MVP.
