# TAILER / TEILER Project Implementation Plan

## 1. Project Summary

**TAILER** is an LLM access-management platform that allows an administrator to connect one or more real LLM provider API keys and create controlled **Sub-API Keys** for individual users, teams, apps, mods, plugins, or clients.

The platform acts as a secure gateway between external clients and LLM providers.

```text
Client App / Hackathon User / Mod / Plugin
        ↓
TAILER Sub-API Key
        ↓
TAILER Gateway
        ↓
Real Provider API Key
        ↓
OpenAI / Anthropic / Gemini / OpenRouter / other providers
```

The purpose of TAILER is to make LLM API usage safer, measurable, configurable, monitorable, limitable, and eventually billable.

The first use case is a hackathon scenario where one shared LLM API key is given to the team, but usage should be separated and monitored per participant.

---

## 2. Core Product Goal

The main goal of the first version is:

> An admin can add one real LLM API key, create multiple Sub-API Keys for users, configure which models they can use, define limits, and monitor their usage.

TAILER should not initially try to become a complete billing system, enterprise gateway, or multi-provider automation platform. The first milestone is a reliable gateway with Sub-API Key management and usage tracking.

---

## 3. MVP Scope

The MVP should include the following features:

1. Admin login
2. User management
3. Project management
4. Provider API key storage
5. Sub-API Key generation
6. Global model configuration
7. Individual model access configuration
8. OpenAI-compatible chat endpoint
9. Usage tracking per Sub-API Key
10. Rate limits and budget limits
11. Admin dashboard
12. User dashboard
13. Basic pipeline configuration
14. API documentation
15. Docker-based local deployment

The MVP should not include full payment billing yet.

---

## 4. Recommended Technology Stack

### Backend

- Python
- FastAPI
- SQLAlchemy or SQLModel
- Alembic for migrations
- Pydantic for validation

### Database

- PostgreSQL

### Cache and Rate Limiting

- Redis

### Frontend

- React or Next.js
- Tailwind CSS or another simple UI framework

### Authentication

- JWT or session-based authentication
- Password hashing with bcrypt or argon2

### Background Processing

For MVP:

- FastAPI background tasks

For later versions:

- Celery or RQ

### Deployment

For MVP:

- Docker Compose

For production:

- Managed PostgreSQL
- Managed Redis
- Container hosting
- HTTPS reverse proxy
- Secrets manager

---

## 5. High-Level Architecture

```text
External Client
    ↓
TAILER API Gateway
    ↓
Sub-Key Authentication
    ↓
Policy Engine
    ↓
Model Router / Pipeline Engine
    ↓
Provider Adapter
    ↓
LLM Provider
    ↓
Usage Metering
    ↓
Database + Dashboard
```

### Main Components

1. **API Gateway**
   - Receives requests from clients.
   - Exposes an OpenAI-compatible API.

2. **Authentication Layer**
   - Validates Sub-API Keys.
   - Validates admin/user dashboard sessions.

3. **Policy Engine**
   - Checks rate limits.
   - Checks budgets.
   - Checks allowed models.
   - Blocks unauthorized requests.

4. **Model Router**
   - Maps public model names to real provider models.
   - Example: `cheap-fast` -> `gpt-4o-mini`.

5. **Provider Adapter**
   - Handles communication with real LLM providers.
   - First provider should be OpenAI or OpenRouter.

6. **Usage Metering**
   - Tracks requests, tokens, costs, errors, and latency.

7. **Dashboard**
   - Allows admins and users to view usage and manage access.

---

## 6. Database Model

The MVP should contain these core tables:

```text
users
organizations
projects
provider_credentials
sub_api_keys
model_configs
limits
pipelines
usage_events
request_logs
```

### users

Stores admin and user accounts.

Fields:

```text
id
email
password_hash
role
created_at
updated_at
```

Roles:

```text
admin
user
```

### organizations

Stores top-level tenant or group data.

Fields:

```text
id
name
created_at
updated_at
```

For a hackathon MVP, there may only be one organization.

### projects

A project can represent a hackathon, app, mod, plugin, client, or internal use case.

Fields:

```text
id
organization_id
name
description
created_at
updated_at
```

### provider_credentials

Stores encrypted real provider API keys.

Fields:

```text
id
project_id
provider_name
encrypted_api_key
status
created_at
updated_at
```

Rules:

- Never store raw API keys.
- Never return provider keys through the API.
- Never log provider keys.

### sub_api_keys

Stores generated TAILER Sub-API Keys.

Fields:

```text
id
project_id
user_id
name
key_hash
key_prefix
status
expires_at
created_at
updated_at
```

Rules:

- Store only a hash of the key.
- Show the full key only once after creation.
- Allow admins to disable or rotate keys.

### model_configs

Defines public model aliases and their real provider targets.

Fields:

```text
id
project_id
public_model_name
provider_name
provider_model_name
enabled
price_input_per_1m_tokens
price_output_per_1m_tokens
created_at
updated_at
```

Example:

```text
public_model_name: cheap-fast
provider_name: openai
provider_model_name: gpt-4o-mini
```

### limits

Defines restrictions per Sub-API Key.

Fields:

```text
id
sub_api_key_id
max_requests_per_minute
max_requests_per_day
max_tokens_per_day
max_cost_per_day
max_cost_per_month
allowed_models
created_at
updated_at
```

### pipelines

Defines routing behavior.

Fields:

```text
id
project_id
name
mode
allowed_models
max_input_tokens
max_output_tokens
fallback_models
created_at
updated_at
```

Initial pipeline modes:

```text
direct
cheap
quality
fallback
restricted
```

### usage_events

Stores usage data for every request.

Fields:

```text
id
request_id
project_id
sub_api_key_id
user_id
provider_name
model
input_tokens
output_tokens
total_tokens
estimated_cost
status
latency_ms
created_at
```

Possible statuses:

```text
success
provider_error
rate_limited
budget_exceeded
invalid_key
model_not_allowed
pipeline_rejected
```

---

## 7. API Design

### Public Gateway Endpoint

The first important endpoint should be OpenAI-compatible:

```http
POST /v1/chat/completions
Authorization: Bearer tailer_sub_key_xxx
Content-Type: application/json
```

Example request:

```json
{
  "model": "cheap-fast",
  "messages": [
    {
      "role": "user",
      "content": "Explain this concept in simple terms."
    }
  ],
  "max_tokens": 500
}
```

Example response:

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
        "content": "Here is a simple explanation..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 80,
    "total_tokens": 180
  }
}
```

---

## 8. Admin API Endpoints

Recommended admin endpoints:

```http
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me

GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PATCH  /api/projects/{id}
DELETE /api/projects/{id}

GET    /api/users
POST   /api/users
GET    /api/users/{id}
PATCH  /api/users/{id}
DELETE /api/users/{id}

GET    /api/provider-credentials
POST   /api/provider-credentials
DELETE /api/provider-credentials/{id}

GET    /api/sub-keys
POST   /api/sub-keys
PATCH  /api/sub-keys/{id}
DELETE /api/sub-keys/{id}
POST   /api/sub-keys/{id}/rotate

GET    /api/models
POST   /api/models
PATCH  /api/models/{id}
DELETE /api/models/{id}

GET    /api/usage
GET    /api/usage/sub-keys/{id}

GET    /api/pipelines
POST   /api/pipelines
PATCH  /api/pipelines/{id}
DELETE /api/pipelines/{id}
```

---

## 9. Frontend Pages

### Admin Interface

Recommended pages:

```text
/login
/admin/dashboard
/admin/projects
/admin/users
/admin/provider-keys
/admin/sub-keys
/admin/models
/admin/pipelines
/admin/usage
/admin/settings
```

The admin dashboard should show:

```text
Total requests today
Total estimated cost today
Total cost this month
Active Sub-API Keys
Top users by usage
Top users by cost
Blocked requests
Provider errors
Recent activity
```

### User Interface

Recommended pages:

```text
/user/dashboard
/user/api-key
/user/usage
/user/docs
```

The user dashboard should show:

```text
Assigned Sub-API Key
Allowed models
Daily usage
Monthly usage
Remaining limits
Example API calls
```

---

## 10. Implementation Phases

### Phase 1: Repository and Environment Setup

Tasks:

1. Create Git repository.
2. Create backend folder.
3. Create frontend folder.
4. Add Docker Compose.
5. Add PostgreSQL service.
6. Add Redis service.
7. Add backend Dockerfile.
8. Add frontend Dockerfile.
9. Add `.env.example`.
10. Add README with local setup instructions.

Expected result:

The project can be started locally with:

```bash
docker compose up
```

### Phase 2: Backend Skeleton

Tasks:

1. Create FastAPI app.
2. Add configuration management.
3. Add database connection.
4. Add Alembic migrations.
5. Add health check endpoint.
6. Add basic error handling.
7. Add logging setup.

Expected endpoints:

```http
GET /health
GET /docs
```

### Phase 3: Authentication

Tasks:

1. Implement user model.
2. Implement password hashing.
3. Implement login endpoint.
4. Implement JWT or session logic.
5. Implement role-based access.
6. Add default admin creation method.

Expected result:

Admin can log in and access protected admin endpoints.

### Phase 4: Project and User Management

Tasks:

1. Implement project CRUD.
2. Implement user CRUD.
3. Link users to projects.
4. Add admin-only permissions.
5. Add basic validation.

Expected result:

Admin can create projects and users.

### Phase 5: Provider Credential Storage

Tasks:

1. Implement provider credential model.
2. Implement encryption service.
3. Add endpoint to store provider keys.
4. Add endpoint to list provider credentials without exposing raw keys.
5. Add endpoint to delete credentials.
6. Add provider credential validation if possible.

Expected result:

Admin can store a real LLM API key securely.

### Phase 6: Sub-API Key Management

Tasks:

1. Implement key generation.
2. Implement key hashing.
3. Store only key hash and prefix.
4. Show full key only once.
5. Add key status: active, disabled, expired.
6. Add key rotation.
7. Add key deletion or disabling.

Expected result:

Admin can create Sub-API Keys for users.

### Phase 7: Model Configuration

Tasks:

1. Implement model config table.
2. Add public model alias.
3. Add real provider model mapping.
4. Add pricing fields.
5. Add enabled/disabled status.
6. Add individual model permissions per key.

Expected result:

Admin can configure global and individual model access.

### Phase 8: First Provider Adapter

Tasks:

1. Create provider adapter interface.
2. Implement one provider first.
3. Recommended first provider: OpenAI or OpenRouter.
4. Add request forwarding.
5. Add response normalization.
6. Extract token usage from provider response.

Expected result:

TAILER can call one real LLM provider from the backend.

### Phase 9: Gateway Endpoint

Tasks:

1. Implement `/v1/chat/completions`.
2. Authenticate Sub-API Key.
3. Validate requested model.
4. Load model mapping.
5. Forward request to provider.
6. Return response to client.
7. Save basic request log.

Expected result:

A user can call TAILER using their Sub-API Key.

### Phase 10: Usage Tracking

Tasks:

1. Implement usage event model.
2. Save event after every request.
3. Save failed requests too.
4. Track tokens and estimated cost.
5. Track latency.
6. Add usage query endpoints.

Expected result:

Admin can see who used how many tokens and estimated costs.

### Phase 11: Rate Limits and Budgets

Tasks:

1. Implement per-minute request limits.
2. Implement daily request limits.
3. Implement daily token limits.
4. Implement daily cost limits.
5. Implement monthly cost limits.
6. Use Redis for fast checks.
7. Use PostgreSQL as source of truth.
8. Block requests before provider call when limits are exceeded.

Expected result:

TAILER prevents uncontrolled usage and cost explosions.

### Phase 12: Admin Dashboard

Tasks:

1. Create login page.
2. Create dashboard page.
3. Show total usage.
4. Show costs.
5. Show active Sub-API Keys.
6. Show top users.
7. Show recent errors.
8. Add key management UI.
9. Add model configuration UI.
10. Add provider key UI.

Expected result:

Admin can manage the platform through a web interface.

### Phase 13: User Dashboard

Tasks:

1. Create user dashboard.
2. Show assigned Sub-API Key.
3. Show allowed models.
4. Show daily and monthly usage.
5. Show API examples.
6. Show limit status.

Expected result:

Users can understand and test their own access.

### Phase 14: Pipeline System

Tasks:

1. Implement pipeline table.
2. Add pipeline selection to Sub-API Keys.
3. Implement direct mode.
4. Implement cheap mode.
5. Implement fallback mode.
6. Implement restricted mode.
7. Add admin UI for pipeline configuration.

Expected result:

Admins can define different LLM usage modes.

### Phase 15: Documentation

Tasks:

1. Add README.
2. Add architecture document.
3. Add API usage examples.
4. Add admin guide.
5. Add user guide.
6. Add cURL examples.
7. Add JavaScript examples.
8. Add Python examples.
9. Add Java example for modding use case.

Expected result:

A developer can integrate TAILER without asking for additional explanation.

### Phase 16: Testing

Minimum tests:

```text
User login works
Admin-only routes are protected
Provider key is encrypted
Sub-API Key is generated correctly
Sub-API Key is stored only as hash
Invalid key is rejected
Disabled key is rejected
Expired key is rejected
Model access is enforced
Rate limit blocks request
Budget limit blocks request
Provider is not called when budget is exceeded
Usage event is created after successful request
Usage event is created after failed request
```

Provider calls should be mocked in tests.

### Phase 17: Deployment Preparation

Tasks:

1. Add production Dockerfile.
2. Add production environment variables.
3. Add database migration command.
4. Add HTTPS reverse proxy configuration.
5. Add health checks.
6. Add backup instructions.
7. Add logging configuration.
8. Add deployment guide.

Expected result:

TAILER can be deployed to a small server or cloud environment.

### Phase 18: Billing Preparation

Do not implement full billing in MVP.

Prepare for billing by ensuring usage events are accurate and immutable.

Later billing features:

```text
Credit balances
Prepaid credits
Usage-based invoices
Stripe integration
Monthly reports
CSV export
Auto-disable when balance is empty
```

---

## 11. Milestones

### Milestone 1: Working Gateway

Goal:

> Admin can create a Sub-API Key, give it to a hackathon user, and the user can call `/v1/chat/completions` while the admin sees usage and can disable the key.

Acceptance criteria:

```text
Admin can log in
Admin can store one provider key
Admin can create one user
Admin can create one Sub-API Key
User can make a chat completion request
Usage event is created
Admin can see usage
Admin can disable the key
Disabled key cannot make requests
```

### Milestone 2: Model Access Control

Goal:

> Admin can configure global and individual model access.

Acceptance criteria:

```text
Admin can define public model aliases
Admin can map aliases to provider models
Admin can assign allowed models to a Sub-API Key
Unauthorized model requests are blocked
Usage is tracked per model
```

### Milestone 3: Basic Pipelines

Goal:

> TAILER supports basic pipelines.

Acceptance criteria:

```text
Admin can create a pipeline
Admin can assign a pipeline to a Sub-API Key
Direct pipeline works
Restricted pipeline blocks invalid requests
Fallback pipeline tries another model if primary model fails
Usage tracking still works correctly
```

---

## 12. Development Guidelines for Human Developers or AI Agents

When implementing this project, follow these rules:

1. Build the smallest working version first.
2. Do not implement billing before metering is reliable.
3. Never expose real provider API keys.
4. Never store API keys as plain text.
5. Never log secrets.
6. Make all limits hard limits.
7. Block invalid requests before calling the provider.
8. Track failed requests too.
9. Keep the API as OpenAI-compatible as reasonably possible.
10. Keep the data model simple in the beginning.
11. Write tests for security and budget behavior.
12. Prefer clear code over clever abstractions.
13. Keep provider-specific logic isolated in provider adapters.
14. Keep usage metering independent from dashboard display.
15. Document every API endpoint with examples.

---

## 13. Recommended Initial Repository Structure

```text
tailer/
  backend/
    app/
      main.py
      config.py
      database.py
      models/
      schemas/
      routes/
      services/
      security/
      providers/
      pipelines/
      tests/
    alembic/
    Dockerfile
    pyproject.toml

  frontend/
    app/
    components/
    lib/
    pages/
    Dockerfile
    package.json

  docs/
    architecture.md
    api.md
    admin-guide.md
    user-guide.md

  docker-compose.yml
  .env.example
  README.md
```

---

## 14. Final Vision

The mature version of TAILER is:

> A managed LLM access-control platform that allows teams, hackathons, app developers, plugin creators, and mod developers to safely distribute LLM access without exposing the real provider API key.

The MVP version is:

> A dashboard that creates limited Sub-API Keys and monitors their usage.

Build the MVP first, then expand into billing, multiple providers, advanced routing, SDKs, and app-specific integrations.
