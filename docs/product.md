# TAILER Product Charter

## One-sentence description

TAILER turns one upstream LLM provider credential into limited, revocable, monitorable Sub-API access for users, teams, and applications.

## First use case

A hackathon organizer has one provider account but many teams need API access. Sharing the upstream key directly makes attribution, revocation, permissions, and cost control difficult.

TAILER sits between client applications and the provider:

~~~text
Client application
  -> TAILER Sub-API key
  -> authentication and policy
  -> provider adapter
  -> LLM provider
  -> usage event
~~~

## Users

### Admin

An admin needs to:

- create a project;
- store one provider credential without exposing it;
- create users;
- issue and revoke Sub-API keys;
- configure allowed models and hard limits;
- inspect usage, failures, and blocked requests.

### User

A user needs to:

- see assigned key metadata;
- see allowed models and remaining limits;
- copy a newly issued key once;
- view personal usage;
- follow concise integration examples.

### Client application

A client is any HTTP-capable program using a Sub-API key. TAILER remains language-independent and does not require a client-side Python library.

## Core product invariants

1. An upstream provider credential never leaves the backend.
2. A stored Sub-API key is a hash, not the raw bearer secret.
3. The raw Sub-API key is shown only in its creation response.
4. Authentication, model access, and limits are checked before a provider call.
5. Every provider attempt produces a durable success or failure usage event.
6. Blocked requests are observable without being charged as provider usage.
7. Prompt and output content are not stored by default.
8. Public runtime behavior stays OpenAI-compatible where practical.
9. Dashboards must describe implemented behavior truthfully.
10. Billing is not built until metering is reliable and auditable.

The current prototype violates some of these target invariants; the implementation plan treats them as explicit gaps.

## MVP scope

The MVP includes:

- admin and user authentication;
- one project;
- one encrypted provider credential;
- user management;
- secure Sub-API-key creation and revocation;
- one real provider adapter;
- `POST /v1/chat/completions`;
- configured model aliases and per-key access;
- request, token, and cost limits;
- durable usage events;
- admin and user usage views;
- repeatable migrations and local deployment;
- integration documentation.

## MVP exclusions

Defer until the core gateway is secure and durable:

- full billing and payments;
- multi-organization tenancy;
- enterprise SSO;
- provider marketplace;
- advanced pipelines;
- RAG and agent orchestration;
- fine-tuning management;
- advanced analytics.

## Product success scenario

The MVP succeeds when a new operator can:

1. start TAILER from documented commands;
2. migrate and seed a clean database;
3. log in as admin;
4. store a provider credential;
5. create a user and limited Sub-API key;
6. call the runtime endpoint from an external client;
7. observe durable usage;
8. verify a disallowed or over-budget request never reaches the provider;
9. revoke the key and see subsequent requests denied.

## Positioning

TAILER is an LLM access-control gateway, not an API-key reseller.

Suggested tagline:

> One provider key. Many controlled users.
