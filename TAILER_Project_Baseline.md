# TAILER / TEILER - Project Baseline and Development Guideline

## 1. Project Name

Working name: **TAILER**

Alternative spelling: **TEILER**

For international communication, the recommended product name is **TAILER** because it is easier to brand in English and can be associated with “tailored access”. The name **TEILER** is still meaningful because it means “divider” or “splitter” in German and directly reflects the technical concept of splitting one LLM API access into controlled sub-accesses.

---

## 2. One-Sentence Description

**TAILER is a web platform that turns one or more real LLM provider API keys into controlled, monitorable, configurable Sub-API Keys for users, teams, apps, mods, plugins, and clients.**

---

## 3. Product Vision

TAILER should become a secure management layer for LLM API access.

The platform allows an admin to connect official LLM provider credentials and then create independent Sub-API Keys with custom limits, permissions, model access, monitoring, and usage reporting.

The first target scenario is a hackathon, where one shared LLM API key is available but must be safely distributed among many participants without exposing the original key.

In the future, the same concept can be used for:

- Indie SaaS products
- Game mods
- Minecraft mods
- Discord bots
- Browser extensions
- WordPress plugins
- Internal company tools
- AI-enabled desktop apps
- Client-specific LLM access
- Educational environments

---

## 4. Problem Statement

LLM APIs are powerful but difficult to manage when multiple users or applications need access.

Typical problems:

- A shared provider API key can be leaked.
- It is difficult to see who used how many tokens.
- It is difficult to enforce individual budgets.
- Users may accidentally use expensive models.
- Admins need to revoke or rotate access quickly.
- Different users may need different models.
- Applications should not contain real provider keys.
- Hackathon teams need easy access without full provider account setup.

TAILER solves these problems by acting as an API gateway and management platform between users and LLM providers.

---

## 5. Core Use Case: Hackathon API Access

Scenario:

A hackathon organizer receives one LLM provider API key for the event. Every participant or team needs LLM access, but giving everyone the original key is unsafe and unmanageable.

TAILER flow:

1. Admin creates a hackathon project in TAILER.
2. Admin stores the real provider API key securely.
3. Admin defines available models and model aliases.
4. Admin creates one Sub-API Key per team or participant.
5. Each Sub-API Key receives limits and permissions.
6. Participants use their Sub-API Keys in their apps.
7. TAILER forwards valid requests to the real provider.
8. TAILER monitors usage per key, team, model, and project.
9. Admin can pause, revoke, or adjust access at any time.
10. Admin can export usage reports after the event.

---

## 6. Target Users

### Primary Users for MVP

- Hackathon organizers
- Hackathon teams
- Developers building quick AI prototypes
- Teachers or course organizers distributing AI API access

### Future Users

- Indie SaaS developers
- Game mod developers
- Plugin developers
- Discord bot developers
- Browser extension developers
- Small companies using multiple AI tools
- Agencies managing AI access for clients

---

## 7. Main Roles

## 7.1 Admin

The Admin owns and manages the project.

Admin capabilities:

- Add real LLM provider API keys
- Create projects
- Create users or teams
- Generate Sub-API Keys
- Set global model configuration
- Set individual user/team model permissions
- Define usage limits
- Define token limits
- Define budget limits
- Monitor all usage
- Revoke or pause Sub-API Keys
- Export usage reports

## 7.2 User

The User receives a Sub-API Key and uses it in their application.

User capabilities:

- View assigned Sub-API Keys
- View allowed models
- View personal usage
- View remaining quota
- Read integration instructions
- Use TAILER API endpoints

## 7.3 Client Application

A Client Application is any software that calls TAILER using a Sub-API Key.

Examples:

- Hackathon prototype
- Web app
- Minecraft mod
- Discord bot
- Browser extension
- WordPress plugin
- Internal automation script

---

## 8. Core Product Requirements

## 8.1 Provider API Key Management

TAILER must allow admins to store real LLM provider API keys.

Requirements:

- Provider keys must be encrypted at rest.
- Provider keys must never be visible to normal users.
- Provider keys should not be returned after creation.
- Admins must be able to disable or rotate provider keys.

MVP provider support:

- Start with one provider only.
- Recommended first provider: OpenAI or OpenRouter.

Future provider support:

- OpenAI
- Anthropic
- Google Gemini
- Mistral
- Azure OpenAI
- OpenRouter
- Local/self-hosted models

---

## 8.2 Sub-API Key Management

TAILER must generate independent Sub-API Keys.

Each Sub-API Key should support:

- Name
- Assigned user/team
- Assigned project
- Allowed models
- Allowed pipelines
- Daily request limit
- Monthly token limit
- Monthly cost/budget limit
- Maximum tokens per request
- Expiration date
- Status: active, paused, revoked, expired

Important:

- The raw Sub-API Key should be shown only once.
- Only a hash of the Sub-API Key should be stored.
- Sub-API Keys must be revocable.

---

## 8.3 Model Configuration

TAILER must allow global and individual model configuration.

### Global Model Configuration

The admin defines which models are available for the whole project.

Example:

```json
{
  "cheap-fast": "openai/gpt-4o-mini",
  "balanced": "openrouter/anthropic/claude-3.5-haiku",
  "premium": "openai/gpt-4.1"
}
```

### Individual Model Configuration

The admin can restrict models for specific users or teams.

Example:

- Team Alpha: `cheap-fast`, `balanced`
- Team Beta: `cheap-fast`
- Organizer Team: `cheap-fast`, `balanced`, `premium`

This prevents users from accidentally using expensive models.

---

## 8.4 API Gateway

TAILER must expose an HTTP API that client applications can call.

The API should be language-independent and usable from any programming language.

Recommended API style:

- REST / JSON
- HTTPS only
- OpenAI-compatible endpoint format where possible

Primary MVP endpoint:

```http
POST /v1/chat/completions
Authorization: Bearer tailer_sub_xxx
Content-Type: application/json
```

---

## 8.5 Usage Monitoring

TAILER must track usage per request.

Minimum tracked fields:

- Timestamp
- Project
- User/team
- Sub-API Key
- Provider
- Model
- Pipeline
- Input tokens
- Output tokens
- Total tokens
- Estimated cost
- Latency
- Status
- Error code, if failed

Admin dashboard should show:

- Total usage
- Usage by user/team
- Usage by model
- Usage over time
- Top users by token usage
- Top users by estimated cost
- Failed requests
- Blocked requests due to limits

User dashboard should show:

- Own usage
- Own remaining limits
- Own available models

---

## 8.6 Limits and Quotas

TAILER must enforce limits before forwarding requests to the real provider.

Minimum MVP limits:

- Requests per minute
- Daily request limit
- Monthly token limit
- Maximum tokens per request
- Allowed models

Recommended additional limits:

- Monthly cost budget
- Daily cost budget
- Pipeline permissions
- Expiration date

Hard rule:

If a limit is reached, TAILER must block the request before calling the real provider.

---

## 8.7 Pipelines

TAILER should support multiple pipelines for working with LLM APIs.

A pipeline is a predefined processing flow for a request.

MVP pipelines:

### Direct Chat

Simple forwarding to the selected model.

```text
Request → Policy Check → Provider → Response
```

### System Prompt Pipeline

Adds a predefined system prompt before forwarding.

```text
Request → Add System Prompt → Provider → Response
```

Future pipelines:

- Moderation pipeline
- JSON output pipeline
- Retrieval-Augmented Generation pipeline
- Tool-calling pipeline
- Agent pipeline
- Summarization pipeline
- Code assistant pipeline

---

## 9. MVP Scope

The MVP should focus on proving the core concept.

## 9.1 Must-Have MVP Features

- Admin login
- User login
- Project creation
- Provider API key storage
- Sub-API Key generation
- OpenAI-compatible chat endpoint
- One real provider integration
- Global model configuration
- Per-user/team model permissions
- Basic rate limits
- Basic token limits
- Basic usage tracking
- Admin usage dashboard
- User usage dashboard
- Key revocation
- Integration documentation

## 9.2 Should-Have MVP Features

- CSV usage export
- Budget estimation
- Per-team usage view
- Key expiration dates
- Basic audit logs
- Example client code

## 9.3 Not Required for MVP

Do not build these in the first version unless the core features already work:

- Stripe billing
- Full multi-provider support
- Advanced RAG
- Advanced agent workflows
- Enterprise SSO
- Organization billing
- Marketplace
- Prompt library
- Fine-tuning tools
- Complex SDK ecosystem

---

## 10. Non-Functional Requirements

## 10.1 Security

Security is critical because TAILER handles real provider credentials.

Requirements:

- Use HTTPS in production.
- Store provider keys encrypted.
- Store Sub-API Keys hashed.
- Never expose real provider keys to users.
- Use role-based access control.
- Validate all input payloads.
- Apply strict rate limits.
- Apply hard quota limits.
- Log administrative actions.
- Do not store full prompts by default.

## 10.2 Reliability

The API Gateway must be stable because all client apps depend on it.

Requirements:

- Return clear error messages.
- Handle provider failures gracefully.
- Store failed requests for debugging.
- Avoid charging usage for failed pre-policy requests.
- Track latency and provider errors.

## 10.3 Performance

MVP performance goals:

- Authentication and policy checks should be fast.
- Rate limits should use Redis or another fast store.
- Usage writes should not significantly slow down response time.
- Streaming support can be added later if not needed immediately.

## 10.4 Privacy

Prompts and outputs may contain sensitive data.

Recommended default:

- Store metadata only.
- Do not store full prompt/output content by default.
- Allow project-level debug logging only when explicitly enabled.
- Clearly document what is stored.

---

## 11. Suggested Tech Stack

Recommended MVP stack:

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy or SQLModel
- Alembic
- PostgreSQL
- Redis

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui or similar UI library

### Infrastructure

- Docker Compose for local development
- PostgreSQL database
- Redis for rate limiting
- Environment variables for secrets
- Reverse proxy for production deployment

---

## 12. Development Principles

Any developer or AI agent working on this project must follow these principles:

## 12.1 Build the Gateway First

The most important feature is the runtime API gateway.

Do not over-focus on dashboards before the gateway works.

Core path:

```text
Sub-API Key → Policy Check → Provider Request → Usage Tracking → Response
```

This must work reliably before advanced features are added.

## 12.2 Keep the API Language-Independent

TAILER must not require clients to use Python.

The backend can be written in Python, but client applications must access TAILER through standard HTTPS/JSON requests.

This allows usage from:

- Java
- Kotlin
- JavaScript
- TypeScript
- C#
- PHP
- Python
- Go
- Rust
- Lua
- Any other language with HTTP support

## 12.3 Prefer OpenAI-Compatible Interfaces

Where possible, TAILER should mimic OpenAI-compatible request and response formats.

Reason:

- Developers already know the format.
- Existing SDKs may work with only a changed base URL.
- Integration friction becomes much lower.

## 12.4 Do Not Expose Real Provider Keys

This is a core rule.

Normal users and client applications must never see the real provider API key.

Only TAILER's backend may use it server-side.

## 12.5 Enforce Limits Before Provider Calls

TAILER must check permissions, rate limits, model access, and budgets before sending a request to the real LLM provider.

This prevents unnecessary cost and abuse.

## 12.6 Keep MVP Small

The MVP should solve one core problem very well:

> Safely distribute and monitor LLM API access through Sub-API Keys.

Do not build a full AI platform before this works.

---

## 13. Recommended Development Roadmap

## Phase 1: Project Foundation

Goal: Create the technical base.

Tasks:

- Initialize backend project
- Initialize frontend project
- Set up Docker Compose
- Set up PostgreSQL
- Set up Redis
- Set up environment configuration
- Create database migrations
- Add basic authentication

Deliverable:

A running local development environment.

---

## Phase 2: Users, Projects, and Provider Keys

Goal: Allow admins to create projects and store provider credentials.

Tasks:

- Create user model
- Create project model
- Create provider credential model
- Encrypt provider credentials
- Add admin endpoints
- Add basic admin UI

Deliverable:

Admin can create a project and store a provider API key.

---

## Phase 3: Sub-API Keys

Goal: Allow admins to create limited Sub-API Keys.

Tasks:

- Create Sub-API Key model
- Generate secure keys
- Store only key hashes
- Show raw key once
- Add revocation
- Add expiration date
- Add owner assignment

Deliverable:

Admin can create a Sub-API Key for a user or team.

---

## Phase 4: API Gateway

Goal: Make the core request flow work.

Tasks:

- Add `/v1/chat/completions`
- Authenticate Sub-API Keys
- Check allowed models
- Route request to provider
- Return provider response
- Handle provider errors

Deliverable:

A user can call TAILER with a Sub-API Key and receive an LLM response.

---

## Phase 5: Usage Tracking

Goal: Track and display usage.

Tasks:

- Create usage event model
- Store request metadata
- Store token usage
- Estimate cost
- Add usage aggregation endpoints
- Add admin usage dashboard
- Add user usage dashboard

Deliverable:

Admin and users can see usage per key/user/team/model.

---

## Phase 6: Limits and Policies

Goal: Prevent abuse and cost explosions.

Tasks:

- Add requests-per-minute limit
- Add daily request limit
- Add monthly token limit
- Add max tokens per request
- Add model restrictions
- Return clear limit errors

Deliverable:

TAILER blocks requests when limits are reached.

---

## Phase 7: Hackathon MVP Polish

Goal: Make the product usable in a real hackathon.

Tasks:

- Add CSV export
- Add onboarding instructions
- Add example cURL request
- Add JavaScript example
- Add Python example
- Add Java example for modding use cases
- Add basic documentation
- Add UI improvements

Deliverable:

TAILER can be used by a hackathon organizer to distribute and monitor LLM API access.

---

## 14. Example API Usage

### cURL Example

```bash
curl https://api.tailer.dev/v1/chat/completions \
  -H "Authorization: Bearer tailer_sub_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cheap-fast",
    "messages": [
      {"role": "user", "content": "Explain what an API gateway is."}
    ],
    "max_tokens": 300
  }'
```

### JavaScript Example

```ts
const response = await fetch("https://api.tailer.dev/v1/chat/completions", {
  method: "POST",
  headers: {
    "Authorization": "Bearer tailer_sub_xxx",
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    model: "cheap-fast",
    messages: [
      { role: "user", content: "Explain recursion simply." }
    ]
  })
});

const data = await response.json();
console.log(data.choices[0].message.content);
```

### Java Example

```java
HttpClient client = HttpClient.newHttpClient();

String body = """
{
  "model": "cheap-fast",
  "messages": [
    {"role": "user", "content": "What should this Minecraft NPC say?"}
  ],
  "max_tokens": 200
}
""";

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.tailer.dev/v1/chat/completions"))
    .header("Authorization", "Bearer tailer_sub_xxx")
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(body))
    .build();

HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);

System.out.println(response.body());
```

---

## 15. Definition of Done for MVP

The MVP is considered complete when:

- An admin can create a project.
- An admin can store one real provider API key.
- An admin can create users or teams.
- An admin can generate Sub-API Keys.
- Users can call `/v1/chat/completions` with their Sub-API Key.
- TAILER forwards valid requests to the real provider.
- TAILER blocks unauthorized or over-limit requests.
- Usage is stored per Sub-API Key.
- Admin can view usage per user/team.
- User can view their own usage.
- Admin can revoke a Sub-API Key.
- Basic documentation exists.

---

## 16. Out-of-Scope for Initial Version

The following features are valuable but should not distract from the MVP:

- Advanced billing
- Stripe payments
- End-user credit marketplace
- Full provider marketplace
- Advanced analytics
- Enterprise roles and permissions
- SSO
- Self-hosted deployment marketplace
- Complex agent pipelines
- Fine-tuning management
- Advanced prompt testing suite

---

## 17. Product Positioning

TAILER should not be described as “reselling API keys”.

Better positioning:

> TAILER is a secure LLM access gateway that helps developers, teams, and organizers distribute controlled AI access without exposing real provider credentials.

Possible taglines:

- Tailored LLM access for every user.
- Split, control, and monitor LLM API usage.
- Safe Sub-API Keys for apps, teams, and hackathons.
- Ship AI access without shipping your real API key.
- One provider key. Many controlled users.

---

## 18. Guidance for AI Agents Working on This Project

When an AI coding agent works on TAILER, it should follow these rules:

1. Preserve the core concept: controlled Sub-API Keys for LLM access.
2. Never expose real provider API keys in frontend code or logs.
3. Build the gateway request flow before advanced UI features.
4. Use clear, simple database models.
5. Keep all runtime request logic auditable.
6. Enforce permissions before calling the external provider.
7. Make all API responses predictable and well-documented.
8. Prefer simple working features over complex abstractions.
9. Keep MVP scope small and hackathon-ready.
10. Document every environment variable and setup step.
11. Use OpenAI-compatible endpoint design where reasonable.
12. Add tests for authentication, key validation, limits, and usage tracking.

---

## 19. Final Product Summary

TAILER is a management and gateway platform for LLM API access.

It allows one real provider API key to be transformed into many controlled Sub-API Keys with independent permissions, limits, model access, pipelines, and usage tracking.

The first MVP should focus on the hackathon scenario:

> One admin, one provider key, many participants, controlled Sub-API Keys, clear usage monitoring.

Once this works, the product can expand toward apps, mods, plugins, SaaS products, education, and client billing.

