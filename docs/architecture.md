# TAILER Architecture

This document separates current implementation from target architecture. For delivery status, use `tasks.md` and the implementation plan.

## Current implementation

~~~text
Next.js browser UI
  -> JWT-authenticated /admin and /user routes
  -> FastAPI
  -> application services and unit of work
  -> SQLAlchemy repositories
  -> PostgreSQL

External client
  -> Sub-API bearer key
  -> POST /v1/chat/completions
  -> HMAC lookup plus active/expiry/project/model checks
  -> project-scoped public-model alias resolution
  -> AES-GCM credential decryption (OpenAI route) or deterministic mock fallback
  -> OpenAIProvider or MockProvider
  -> normalized response or sanitized provider error
  -> durable success or provider-failure usage write
~~~

PostgreSQL is the default runtime adapter. A copy-on-write in-memory adapter is
retained for isolated tests; the complete API contract suite runs against both
it and a fresh Alembic-migrated SQL database. Compose migrates to Alembic head
and seeds deterministic demo records before starting the API.

Implemented security behavior includes hashed dashboard passwords and generated
high-entropy Sub-API keys whose HMAC digest is stored. The raw Sub-API key is
returned only by its creation response; later reads expose a safe display
fragment. Provider credentials are encrypted with AES-256-GCM using a versioned
operator keyring. Authenticated associated data binds ciphertext to its
credential ID, project ID, provider, and key version, so moving encrypted data
to a different identity or scope fails authentication. Admin responses expose
only safe credential metadata.

Alembic head `0003` adds `provider_credentials` and `model_configs`. An enabled
model configuration maps a public alias to a concrete provider model,
credential, and input/output EUR prices. The OpenAI Chat Completions adapter and
its normalized error paths pass mocked-upstream integration tests. The mock
fallback remains deterministic for the unconfigured development seed. A live
configured encrypted route to a deliberately non-routable HTTPS upstream also
verified sanitized `provider_unavailable` handling, durable failure persistence
across restart, and API/log redaction. PostgreSQL reached `0003` through a clean
upgrade/check/downgrade/re-upgrade. A successful request to OpenAI with a
disposable real credential has not yet been verified and is the sole Iteration
2 acceptance gap. Rate, token, cost, and per-request maximum-token policy
enforcement plus pre-provider blocked-event writes remain future slices.

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
- `GET|POST /admin/provider-credentials`
- `DELETE /admin/provider-credentials/{credential_id}`
- `GET|POST /admin/model-configs`
- `DELETE /admin/model-configs/{config_id}`
- `GET /admin/usage`

Provider-credential responses are metadata-only; create accepts a secret but
neither create/list/revoke responses nor model-configuration responses contain
plaintext or ciphertext. The two `DELETE` routes revoke/disable rather than
erasing audit-relevant configuration. New project endpoints should remain under
`/admin` for this API generation.

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

Current dashboard auth:

- hashed user passwords;
- configured JWT secret, algorithm, and expiration;
- stable `sub` claim;
- role lookup from persisted user state;
- no refresh/session flow yet.

Current runtime auth:

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
5. Resolve the enabled alias, provider credential, provider model, and pricing.
6. Reserve/check rate and budget policy.
7. Invoke the provider adapter.
8. Normalize response and usage or a sanitized provider failure.
9. Persist success or provider-failure usage.
10. Commit counters and return a stable response.
~~~

Steps 1-6 must eventually complete before an upstream call.

The current slice implements steps 1-5 and 7-9: it resolves an alias before
I/O, decrypts a backend-held credential only for the selected route, normalizes
provider failures, and durably writes their sanitized stable `error_code`.
Step 6 and counter commits are not implemented; consequently configured rate
and budget fields remain descriptive rather than enforced. Requests rejected
before provider invocation are not yet written as blocked audit events.

## Service and repository boundaries

Routes coordinate HTTP concerns and delegate to focused services/repositories for:

- users and dashboard identity;
- projects;
- Sub-API keys;
- provider credentials;
- model configurations;
- usage events.

The current unit of work owns one transaction at a time. SQLAlchemy uses one
Session per operation. The test-only memory implementation uses a serialized,
copy-on-write transaction with explicit commit semantics. Neither adapter holds
a transaction open during provider I/O.

Provider resolution performs repository reads in a short unit of work, closes
it before upstream I/O, then records success or provider failure in a separate
transaction. Policy decisions join these boundaries in a later iteration.

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

- `id`
- `project_id`
- provider and display name
- encrypted credential ciphertext and key version
- safe suffix hint
- status
- timestamps

Never return ciphertext or raw credential values.

### model_configs

- `id`
- `project_id`
- public alias
- provider and provider model
- credential reference
- enabled state
- input/output pricing metadata
- timestamps

## Frozen API-to-ORM mappings

Iteration 1 uses these explicit mappings:

| API boundary | Domain and persistence mapping |
| --- | --- |
| Key creation omits `project_id` | Assign configured `TAILER_DEFAULT_PROJECT_ID`; the seeded default is `proj_hackathon_2026`. Never infer the first project. |
| `POST /admin/keys` raw `key` | Return the generated bearer once in the creation response. Store only an HMAC-SHA-256 digest and a safe display fragment. |
| Key GET/list responses | Expose `key_prefix`; never expose or reconstruct the raw bearer. |
| Usage `timestamp` | Map to UTC-aware `created_at` and serialize as an ISO `Z` string. |
| Usage `sub_key_id` | Map to internal and ORM `sub_api_key_id`. |
| Usage omits project/provider metadata | Copy `project_id` and `user_id` from the authorized key; persist the provider identifier, public model, provider model, and `EUR` currency. |
| Provider credential create body | Encrypt the one supplied plaintext secret before persistence. Return only metadata, including a masked suffix hint and key version; never serialize plaintext or ciphertext. |
| Runtime public model | Resolve the enabled `(project_id, public_model)` configuration to its provider, provider model, credential, and configured EUR token prices. |
| Provider failure | Return a stable sanitized error object and durably persist a zero-token event with `failed` or `rate_limited` status and its stable `error_code`. |

Sub-API-key digests use a dedicated `TAILER_SUB_API_KEY_PEPPER`, separate from JWT signing secrets. Changing the pepper invalidates existing bearer keys and therefore requires an intentional rotation plan.

The deterministic demo seed runs after Alembic, inserts rows in foreign-key order, and never overwrites compatible existing rows. It aborts and rolls back on fixed-ID or normalized-email collisions. Demo key expiry is fixed at the end of 2099 so the seed does not become date-dependent.

Routes depend on application services backed by a unit-of-work factory. The
in-memory adapter owns a serialized copy-on-write store with explicit commit and
rollback; the SQLAlchemy adapter owns one Session per unit of work. Repositories
do not commit or raise HTTP errors. Runtime authorization closes its read
transaction before provider I/O, then usage is written in a separate short
transaction before a success response is returned.

## Provider boundary

`backend/app/providers.py` is the correct abstraction point.

A provider adapter must:

- accept normalized messages and generation options;
- use only backend-held credentials;
- return normalized choices and token usage;
- expose typed provider failures;
- support test substitution;
- avoid logging secrets or prompt content by default.

`OpenAIProvider` is the first real adapter and calls the OpenAI Chat Completions
endpoint with a server-side bearer credential. It maps upstream HTTP,
connection, timeout, and response-shape failures to stable public errors without
copying upstream bodies into client responses or logs. Configured per-million-
token EUR rates drive estimated cost. Its request/response integration is
verified against a mocked upstream, and its connection-failure path has been
verified through the live Compose stack without secret leakage. A successful
disposable real-credential smoke is still required. Multi-provider routing
follows only after this exit gate is closed.

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

Record metadata for successful, failed, and blocked requests. Success and
provider-failure metadata are implemented; blocked-request persistence is not.
Do not store full prompts or outputs by default.

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

The current frontend has no provider-credential or model-configuration
management screen. Those operations are available only through authenticated
admin API calls.

## Deployment shape

Local development uses Compose services for:

- PostgreSQL
- Redis
- FastAPI backend
- Next.js frontend

`tailer.cmd` is the interactive/command-line Windows controller and `tailer.sh`
is the Unix controller for start, stop, restart, status, logs, and configuration
validation. `deploy/systemd/tailer.service` wraps the Unix controller for a
rootful Docker host installed at `/opt/tailer`.

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
