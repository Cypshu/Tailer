# TAILER / TEILER - Program Architecture

## 1. Product Summary

**TAILER** is a web platform for managing, splitting, monitoring, and controlling access to Large Language Model (LLM) APIs.

The platform allows an administrator to connect one or more real provider API keys, such as OpenAI, Anthropic, Google Gemini, Mistral, Azure OpenAI, or OpenRouter. TAILER then creates controlled **Sub-API Keys** for individual users, teams, apps, clients, hackathon participants, mods, plugins, or internal tools.

Instead of giving every participant or client direct access to the real provider API key, TAILER acts as a secure gateway between the user and the LLM provider.

```text
Client App / User / Plugin / Mod
        ↓
TAILER Sub-API Key
        ↓
TAILER API Gateway
        ↓
Policy, Limits, Model Routing, Usage Tracking
        ↓
Real LLM Provider API
```

The first practical use case is a hackathon environment where a shared provider API key is available, but the organizer needs to distribute controlled access to many participants while monitoring each participant's usage.

---

## 2. Core Problem

In many environments, teams or developers receive one shared LLM API key. This creates several problems:

- The real API key must not be exposed to every user.
- Usage cannot easily be tracked per person, team, app, or project.
- Costs can grow unpredictably.
- Different users may need different model permissions.
- Some users should have access to powerful models, while others should only use cheaper models.
- Admins need a simple way to revoke, rotate, limit, or inspect API access.
- Apps, mods, plugins, and client applications need a safe way to use LLMs without embedding the real provider key.

TAILER solves this by creating a controlled abstraction layer above the real provider API.

---

## 3. Core Concept

TAILER receives requests from users through generated Sub-API Keys. Each Sub-API Key has its own configuration:

- Assigned user or team
- Allowed models
- Request limits
- Token limits
- Budget limits
- Expiration date
- Pipeline configuration
- Logging rules
- Status: active, paused, revoked, expired

When a request arrives, TAILER checks the key, validates the policy, routes the request to the correct provider/model, stores usage data, and returns the response to the client.

---

## 4. High-Level System Architecture

```text
Frontend Dashboard
  ├── Admin Interface
  └── User Interface

Backend API
  ├── Authentication Service
  ├── Sub-Key Management Service
  ├── Provider Credential Vault
  ├── API Gateway
  ├── Policy Engine
  ├── Model Router
  ├── Pipeline Engine
  ├── Usage Metering Service
  ├── Billing / Cost Estimation Service
  ├── Audit Logging Service
  └── Notification / Webhook Service

Data Layer
  ├── PostgreSQL
  ├── Redis
  └── Object Storage, optional

External Services
  ├── OpenAI API
  ├── Anthropic API
  ├── Google Gemini API
  ├── Mistral API
  ├── OpenRouter API
  └── Other LLM Providers
```

---

## 5. Recommended Technology Stack

### Backend

Recommended: **Python + FastAPI**

Reasons:

- Fast development speed
- Strong API support
- Automatic OpenAPI documentation
- Good async support
- Good fit for LLM routing and backend orchestration
- Easy integration with PostgreSQL, Redis, Celery/RQ, and provider SDKs

Suggested backend components:

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy or SQLModel
- Alembic for migrations
- PostgreSQL
- Redis for rate limiting and caching
- Celery, RQ, or Dramatiq for background jobs
- Uvicorn/Gunicorn for deployment

### Frontend

Recommended: **React / Next.js**

Reasons:

- Good dashboard experience
- Strong ecosystem
- Easy auth integration
- Suitable for admin and user portals

Suggested frontend components:

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui or similar component library
- Recharts or similar charting library

### Infrastructure

For the MVP:

- Docker Compose
- PostgreSQL container
- Redis container
- Backend container
- Frontend container

For production:

- Managed PostgreSQL
- Managed Redis
- Container hosting, Kubernetes, Fly.io, Render, Railway, Hetzner, AWS, Azure, or GCP
- HTTPS via reverse proxy or platform-managed TLS

---

## 6. Main Components

## 6.1 Frontend Dashboard

The frontend has two main areas:

### Admin Interface

The Admin Interface allows organizers or platform owners to manage the system.

Core functions:

- Create and manage projects
- Add provider API keys
- Create users or teams
- Generate Sub-API Keys
- Define global model settings
- Define individual user/team model settings
- Set rate limits and budgets
- Monitor total and per-user usage
- View logs and errors
- Revoke or rotate keys
- Export usage data

### User Interface

The User Interface allows individual users to inspect their access.

Core functions:

- View assigned Sub-API Keys
- See allowed models
- See remaining usage quota
- View personal request/token usage
- Read integration instructions
- Copy example code
- Request access or higher limits, optional

---

## 6.2 Authentication and Authorization Service

The platform should support at least two authentication levels:

### Admin Authentication

Admins can:

- Manage provider keys
- Manage users
- Configure projects
- View all usage
- Revoke any Sub-API Key
- Configure global policies

### User Authentication

Users can:

- View their own keys
- View their own usage
- Use their Sub-API Key to call the gateway
- Not see real provider credentials

Recommended MVP authentication:

- Email/password authentication
- JWT or secure session cookies
- Role-based access control: `admin`, `user`

Future authentication options:

- OAuth login
- GitHub login for hackathons
- Google login
- SSO for enterprise environments

---

## 6.3 Provider Credential Vault

The Provider Credential Vault stores real provider API keys.

Important requirements:

- Provider keys must never be exposed to users.
- Provider keys must be encrypted at rest.
- Provider keys should not be returned in API responses after creation.
- Admins should be able to rotate provider keys.
- Provider keys should be scoped to projects where possible.

Example provider credential:

```json
{
  "id": "prov_123",
  "project_id": "proj_hackathon_2026",
  "provider": "openai",
  "name": "Hackathon OpenAI Key",
  "encrypted_api_key": "...",
  "status": "active"
}
```

---

## 6.4 Sub-API Key Management Service

The Sub-Key Management Service creates and manages controlled access keys.

A Sub-API Key is not the real provider key. It is a TAILER-generated key that identifies a user, team, app, or client.

Example Sub-Key configuration:

```json
{
  "id": "subkey_123",
  "name": "Team Alpha Hackathon Key",
  "owner_type": "team",
  "owner_id": "team_alpha",
  "project_id": "proj_hackathon_2026",
  "allowed_models": ["gpt-4o-mini", "gpt-4.1-mini"],
  "daily_request_limit": 500,
  "monthly_token_limit": 1000000,
  "monthly_budget_eur": 10.00,
  "max_tokens_per_request": 2000,
  "expires_at": "2026-12-31T23:59:59Z",
  "status": "active"
}
```

Security requirements:

- Store only hashed Sub-API Keys in the database.
- Show the raw Sub-API Key only once during creation.
- Support key revocation.
- Support key rotation.
- Support expiration dates.

---

## 6.5 API Gateway

The API Gateway is the central runtime component.

Responsibilities:

1. Receive incoming requests.
2. Extract the Sub-API Key from the `Authorization` header.
3. Authenticate the Sub-API Key.
4. Load the policy for the key.
5. Validate rate limits, budgets, and model permissions.
6. Normalize the request format.
7. Route the request to the selected provider.
8. Receive the provider response.
9. Calculate usage and costs.
10. Store usage events.
11. Return the response to the client.

Recommended primary endpoint:

```http
POST /v1/chat/completions
Authorization: Bearer tailer_sub_xxx
Content-Type: application/json
```

The MVP should aim to be compatible with the OpenAI Chat Completions format or the modern Responses API style where possible.

---

## 6.6 Policy Engine

The Policy Engine decides whether a request is allowed.

Policy checks:

- Is the Sub-API Key active?
- Has the key expired?
- Is the requested model allowed?
- Has the user exceeded the rate limit?
- Has the user exceeded the token limit?
- Has the user exceeded the budget?
- Is the requested max token count allowed?
- Is the requested pipeline allowed?

Example decision:

```json
{
  "allowed": false,
  "reason": "monthly_budget_exceeded",
  "message": "This Sub-API Key has reached its monthly budget limit."
}
```

---

## 6.7 Model Router

The Model Router maps user-facing model names to real provider models.

Example:

```json
{
  "cheap-fast": {
    "provider": "openai",
    "model": "gpt-4o-mini"
  },
  "balanced": {
    "provider": "openrouter",
    "model": "anthropic/claude-3.5-haiku"
  },
  "best": {
    "provider": "openai",
    "model": "gpt-4.1"
  }
}
```

This allows the admin to change the actual provider model without changing client code.

A client can request:

```json
{
  "model": "cheap-fast",
  "messages": [
    {"role": "user", "content": "Explain this bug."}
  ]
}
```

TAILER internally routes `cheap-fast` to the configured provider and model.

---

## 6.8 Pipeline Engine

TAILER should support different pipelines for working with LLM APIs.

A pipeline is a predefined processing flow around the LLM request.

Example pipelines:

### Direct Chat Pipeline

Simple request forwarding to a model.

```text
Client Request → Policy Check → Provider Request → Response
```

### System Prompt Pipeline

Adds a predefined system prompt before forwarding.

```text
Client Request → Inject System Prompt → Provider Request → Response
```

### Moderated Pipeline

Checks user input before forwarding.

```text
Client Request → Moderation Check → Provider Request → Response
```

### JSON Output Pipeline

Enforces structured JSON output.

```text
Client Request → Add JSON Schema Instructions → Provider Request → Validate JSON → Response
```

### RAG Pipeline, future

Adds retrieval from documents or knowledge bases.

```text
Client Request → Retrieve Context → Build Prompt → Provider Request → Response
```

For the MVP, implement only:

- Direct Chat Pipeline
- System Prompt Pipeline

---

## 6.9 Usage Metering Service

The Usage Metering Service records every successful and failed request.

Usage data is the core value of the platform.

Each request should create a usage event:

```json
{
  "id": "usage_123",
  "timestamp": "2026-07-04T12:00:00Z",
  "project_id": "proj_hackathon_2026",
  "sub_key_id": "subkey_123",
  "user_id": "user_123",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "pipeline": "direct_chat",
  "input_tokens": 520,
  "output_tokens": 180,
  "total_tokens": 700,
  "estimated_cost_eur": 0.0021,
  "latency_ms": 820,
  "status": "success"
}
```

Usage should be queryable by:

- Project
- User
- Team
- Sub-Key
- Model
- Provider
- Date range
- Pipeline

---

## 6.10 Billing and Cost Estimation Service

For the hackathon MVP, billing does not need to charge users directly.

The MVP should support:

- Cost estimation per request
- Aggregated cost per user/team
- Budget limits
- Exportable usage reports

Future billing features:

- Prepaid credits
- Stripe integration
- Usage-based billing
- Invoices
- Team budgets
- Reseller or client billing

---

## 6.11 Logging and Audit Service

The system should log important actions:

- Admin created a provider key
- Admin created a Sub-API Key
- User exceeded a limit
- Key was revoked
- Model configuration changed
- Usage export was generated

Prompt logging should be configurable because it may contain sensitive information.

Recommended default:

- Store metadata by default.
- Do not store full prompts unless explicitly enabled.
- Allow admins to enable request/response logging per project for debugging.

---

## 7. Database Model

Recommended core tables:

```text
users
organizations
projects
provider_credentials
sub_api_keys
model_mappings
pipelines
policies
usage_events
audit_logs
api_requests
```

### users

```text
id
email
password_hash
role
created_at
updated_at
```

### projects

```text
id
organization_id
name
description
status
created_at
updated_at
```

### provider_credentials

```text
id
project_id
provider
name
encrypted_api_key
status
created_at
updated_at
```

### sub_api_keys

```text
id
project_id
owner_user_id
name
key_hash
allowed_models
allowed_pipelines
rate_limit_per_minute
daily_request_limit
monthly_token_limit
monthly_budget_eur
max_tokens_per_request
expires_at
status
created_at
updated_at
```

### model_mappings

```text
id
project_id
public_model_name
provider
provider_model_name
provider_credential_id
status
created_at
updated_at
```

### usage_events

```text
id
project_id
sub_api_key_id
user_id
provider
model
pipeline
input_tokens
output_tokens
total_tokens
estimated_cost_eur
latency_ms
status
error_code
created_at
```

---

## 8. API Design

## 8.1 Runtime API

### Chat Completion Endpoint

```http
POST /v1/chat/completions
Authorization: Bearer tailer_sub_xxx
Content-Type: application/json
```

Request:

```json
{
  "model": "cheap-fast",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain recursion in simple words."}
  ],
  "max_tokens": 500,
  "temperature": 0.7
}
```

Response:

```json
{
  "id": "chatcmpl_tailer_123",
  "object": "chat.completion",
  "model": "cheap-fast",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Recursion is when a function calls itself to solve smaller parts of a problem."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 18,
    "total_tokens": 38
  }
}
```

---

## 8.2 Admin API

### Create Sub-API Key

```http
POST /admin/projects/{project_id}/sub-keys
Authorization: Bearer admin_jwt
```

Request:

```json
{
  "name": "Team Alpha",
  "owner_user_id": "user_123",
  "allowed_models": ["cheap-fast", "balanced"],
  "daily_request_limit": 500,
  "monthly_token_limit": 1000000,
  "monthly_budget_eur": 10.0,
  "expires_at": "2026-12-31T23:59:59Z"
}
```

Response:

```json
{
  "id": "subkey_123",
  "name": "Team Alpha",
  "api_key": "tailer_sub_xxxxxxxxx",
  "warning": "This key is shown only once. Store it securely."
}
```

### Get Usage

```http
GET /admin/projects/{project_id}/usage?from=2026-07-01&to=2026-07-04
Authorization: Bearer admin_jwt
```

---

## 9. Rate Limiting Strategy

Use Redis for fast counters.

Suggested dimensions:

- Requests per minute per Sub-Key
- Requests per day per Sub-Key
- Tokens per month per Sub-Key
- Budget per month per Sub-Key
- Global project limit

Rate limit checks should happen before calling the external provider.

---

## 10. Security Requirements

Minimum requirements:

- HTTPS only
- Hash Sub-API Keys before storing
- Encrypt real provider API keys
- Role-based access control
- Never expose provider keys to users
- Support key revocation
- Store audit logs
- Apply strict rate limits
- Apply hard budget limits
- Validate all incoming payloads
- Avoid logging sensitive prompts by default
- Use environment variables for secrets

Security mindset:

In distributed apps, mods, plugins, desktop apps, and browser extensions, any client-side key can eventually be extracted. Therefore, Sub-API Keys must be treated as limited and revocable access tokens, not as perfectly secret credentials.

---

## 11. MVP Architecture

For the first version, build only what is necessary for the hackathon use case.

### MVP Components

- Admin login
- User login
- Project creation
- Provider key storage
- Sub-API Key creation
- OpenAI-compatible chat endpoint
- Model mapping
- Basic global model configuration
- Basic individual user model configuration
- Usage tracking
- Admin usage dashboard
- User usage dashboard
- Key revocation
- Basic rate limits

### MVP Exclusions

Do not build initially:

- Full billing system
- Stripe integration
- Complex RAG pipelines
- Multi-organization enterprise features
- Marketplace
- Fine-tuning management
- Agent orchestration
- Advanced prompt management
- Team-based SSO

---

## 12. Suggested Development Milestones

### Milestone 1: Backend Foundation

- Create FastAPI project
- Configure PostgreSQL
- Configure migrations
- Implement user model
- Implement project model
- Implement authentication

### Milestone 2: Provider and Sub-Key Management

- Add provider credential storage
- Encrypt provider keys
- Add Sub-API Key creation
- Hash Sub-API Keys
- Implement Sub-Key authentication

### Milestone 3: API Gateway

- Implement `/v1/chat/completions`
- Validate Sub-API Key
- Check model permissions
- Forward request to one provider
- Return provider response

### Milestone 4: Usage Tracking

- Record usage events
- Estimate token usage and cost
- Create admin usage endpoints
- Create user usage endpoints

### Milestone 5: Frontend Dashboard

- Admin dashboard
- User dashboard
- Key management UI
- Usage charts
- Model configuration UI

### Milestone 6: Hackathon Readiness

- Add rate limits
- Add budget limits
- Add export function
- Add documentation
- Add example clients

---

## 13. Example Hackathon Flow

1. Hackathon organizer creates a TAILER project.
2. Organizer adds the real provider API key.
3. Organizer defines available models:
   - `cheap-fast`
   - `balanced`
   - `premium`
4. Organizer creates teams or users.
5. TAILER generates one Sub-API Key per team.
6. Participants use the Sub-API Key in their apps.
7. TAILER tracks usage per team.
8. Organizer can see which team used which model and how many tokens.
9. If a team exceeds the limit, TAILER blocks further requests.
10. Organizer exports the final usage report.

---

## 14. Naming Note

The product name can be written as **TAILER** or **TEILER**.

Possible interpretations:

- **TEILER**: German for “divider” or “splitter”, which fits the idea of splitting one API access into controlled sub-accesses.
- **TAILER**: More international and brandable, close to “tailor”, suggesting a tailored API access layer.

Recommended branding for international use:

**TAILER**

Possible tagline:

> Tailored LLM access for teams, apps, and users.

Alternative German-inspired tagline:

> Split, control, and monitor LLM API access.

---

## 15. Architectural Principle

TAILER should not be built as a Python library that other applications import.

TAILER should be built as a language-independent HTTP API service.

This allows clients written in Java, JavaScript, TypeScript, C#, PHP, Python, Go, Rust, Lua, Kotlin, or any other language to use it through standard HTTPS requests.

The backend may be written in Python, but the integration surface must remain universal.

