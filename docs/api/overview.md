# API Overview

## Purpose

ECI Platform exposes a REST API for analyzing business communications: producing a summary, priority classification, category, action items, and an optional draft reply. Analysis is performed by a configurable `AIProvider` behind the scenes (see [Provider Abstraction](../architecture/provider-abstraction.md)). When persistence is configured and the caller is authenticated, a successful analysis can be stored as user-owned history. Authenticated callers with `communications:workflow` can propose and approve or reject a `WorkflowAction` derived from a stored draft. Authenticated callers with `communications:send` can execute an already-approved action. Approval authorizes a stored snapshot; execute sends that snapshot through the owned mailbox account. There is no retry route and no automatic reply.

## Base URL

When run locally with the default configuration:

```text
http://localhost:8000
```

`APP_HOST` and `APP_PORT` (see `app/core/config.py`) control the bind address; `8000` is the default `APP_PORT`.

## API Versioning

Versioned endpoints are served under a configurable prefix, `API_V1_PREFIX`, which defaults to `/api/v1`. The prefix is read once from `Settings` and applied in `app/api/router.py`; it is not hard-coded in individual route modules.

The root liveness endpoint (`GET /health`) is intentionally unversioned, matching the platform-level health check convention.

## Content Type

All request and response bodies use `application/json`. Request bodies are validated against Pydantic v2 models; malformed or non-conforming JSON is rejected with an HTTP `422` response.

## OpenAPI and Swagger UI

FastAPI generates OpenAPI documentation automatically from the route definitions and Pydantic schemas.

Development and tests:

- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI schema: `GET /openapi.json`

When `APP_ENV=production`, those documentation routes are disabled.

No manual OpenAPI authoring is required or performed; the schema reflects the current route and model definitions exactly.

## Authentication Status

Application-user authentication is implemented as provider-independent JWT bearer validation. Live Microsoft Entra ID is the first identity provider. ECI remains IdP-agnostic in application code. Production clouds use `AUTH_MODE=oidc`.

When persistence is configured, a verified `(issuer, subject)` maps to an opaque internal user UUID used as the ownership key. Email is not used as an identifier. That mapping is user-associated ownership, not SaaS tenancy.

```text
Client
  → Authorization: Bearer <JWT>
  → ECI validates signature, issuer, audience, and expiry
  → ECI requires the route-specific permission
  → POST /api/v1/communications/analyze (communications:analyze)
  → GET/DELETE /api/v1/analyses (communications:analyze)
  → POST/GET /api/v1/workflow-actions (communications:workflow)
  → POST /api/v1/workflow-actions/{id}/execute (communications:send)
  → GET /api/v1/connector-accounts/{id}/messages (communications:read)
  → POST /api/v1/connector-accounts/{id}/messages/analyze (communications:read + communications:analyze)
```

Configuration (`app/core/config.py`):

- `AUTH_MODE=disabled` — allowed in development and tests; analyze does not require a token and does not persist owned history
- `AUTH_MODE=oidc` — requires `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`
- `APP_ENV=production` requires `AUTH_MODE=oidc` (fail closed)

This is **not** cloud workload identity and **not** database identity. Foundry Managed Identity and the ECS Task Role authenticate ECI to AI platforms. PostgreSQL credentials authenticate ECI to the database. The caller's OIDC token does not authenticate to PostgreSQL.

Public (no token):

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/readiness`

Protected when `AUTH_MODE=oidc`:

- `POST /api/v1/communications/analyze`

Always require an authenticated principal (including `AUTH_MODE=disabled`, which returns `401`):

- `GET /api/v1/analyses`
- `GET /api/v1/analyses/{analysis_id}`
- `DELETE /api/v1/analyses/{analysis_id}`
- `POST /api/v1/workflow-actions`
- `GET /api/v1/workflow-actions`
- `GET /api/v1/workflow-actions/{action_id}`
- `POST /api/v1/workflow-actions/{action_id}/approve`
- `POST /api/v1/workflow-actions/{action_id}/reject`
- `POST /api/v1/workflow-actions/{action_id}/execute` (`communications:send`)
- `POST /api/v1/connector-accounts/gmail/authorize` (`communications:connect`)
- `GET /api/v1/oauth/callbacks/gmail` (no ECI bearer; ownership from the authorization session)
- `POST /api/v1/connector-accounts/microsoft_graph/authorize` (`communications:connect`)
- `GET /api/v1/oauth/callbacks/microsoft_graph` (no ECI bearer; ownership from the authorization session)
- `POST /api/v1/connector-accounts/{connector_account_id}/disconnect` (`communications:connect`)
- `POST /api/v1/connector-accounts/{connector_account_id}/reauthorize` (`communications:connect`)
- `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze` (`communications:read` + `communications:analyze`)
- `GET /api/v1/connector-accounts/{connector_account_id}/messages` (`communications:read`)

Mailbox-backed analyze and bounded mailbox listing always require an authenticated principal (`AUTH_MODE=disabled` returns `401`). Direct-text `POST /api/v1/communications/analyze` still requires only `communications:analyze` and does not use connector accounts. Listing requires `communications:read` and does not require `communications:analyze`.

`GET /api/v1/oauth/callbacks/gmail` and `GET /api/v1/oauth/callbacks/microsoft_graph` are provider redirect targets and do not use the ECI bearer token. CONNECT versus REAUTHORIZE is taken from the consumed authorization session. Reauthorization requires the verified mailbox identity to match the bound account.

Missing or invalid tokens return `401` with `WWW-Authenticate: Bearer`. A valid token without the route permission returns `403`. History routes reuse `communications:analyze`. Workflow proposal/approval routes require `communications:workflow`. Execute requires `communications:send`. Mailbox authorize, disconnect, and reauthorize require `communications:connect`. Mailbox-backed analyze requires `communications:read` and `communications:analyze`. Bounded mailbox listing requires `communications:read`. Analyze, workflow, send, connect, and read do not imply each other. Direct-text analyze does not require `communications:read`. Unknown and cross-user analysis, workflow, or connector-account resources return `404`, not `403`. History, workflow, and mailbox-OAuth routes without `DATABASE_URL` return `503`.

Permissions are read only from bounded claims `scp`, `scope`, or `roles`. Internal users store only `issuer` and `subject`; they are not a session store or login database.

## Provider Status

The API resolves an `AIProvider` through configuration (`AI_PROVIDER`, default `mock`). Supported values are `mock`, `microsoft_foundry`, and `amazon_bedrock`. The REST request and response schemas do not change with the selected provider. Automated tests and the default local configuration use `MockAIProvider`. See [Provider Abstraction](../architecture/provider-abstraction.md), [Microsoft Foundry](../cloud/azure-ai-foundry.md), and [Amazon Bedrock](../cloud/amazon-bedrock.md).

## Request Correlation

Every HTTP response includes `X-Request-ID`. The server generates a UUID `request_id` for the request, binds it through `structlog.contextvars`, and returns it on the response. An incoming `X-Request-ID` is ignored. The value is operational correlation only; it is not part of JSON response schemas. `message_id` in analysis requests remains business metadata and is separate.

See [Observability](../cloud/observability.md).

## Request Flow (High Level)

```text
Client
  ↓ HTTP request
request_id middleware
  ↓
FastAPI route (app/api/routes/*)
  ↓ dependency injection
  ├── CommunicationAnalysisWorkflowService (direct-text analyze / history)
  ├── ConnectedMailboxMessageListingService (bounded mailbox list)
  ├── ConnectedMailboxAnalysisService (mailbox-backed analyze)
  ├── WorkflowActionService (workflow proposal and approval)
  ├── WorkflowActionExecutionService (execute)
  └── mailbox OAuth services (Gmail/Microsoft connect/callback; disconnect; reauthorize)
```

Routes validate the incoming request via Pydantic, resolve a workflow, execution, mailbox-list, mailbox-analyze, or mailbox-OAuth service through FastAPI dependencies, and return the result. Phase 14 mounts bounded mailbox listing and mailbox-backed analyze. Phase 13 adds mailbox OAuth lifecycle HTTP. Phase 12E reaches Graph and Gmail writers only through `POST /api/v1/workflow-actions/{action_id}/execute`. See [Endpoints](endpoints.md) for the concrete routes, [Persistence](../architecture/persistence.md) for ownership and failure semantics, and [Sequence Diagrams](../architecture/sequence-diagrams.md) for a step-by-step walkthrough.
