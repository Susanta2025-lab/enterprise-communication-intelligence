# API Overview

## Purpose

ECI Platform exposes a REST API for analyzing business communications: producing a summary, priority classification, category, action items, and an optional draft reply. Analysis is performed by a configurable `AIProvider` behind the scenes (see [Provider Abstraction](../architecture/provider-abstraction.md)). When persistence is configured and the caller is authenticated, a successful analysis can be stored as user-owned history.

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
  → ECI requires permission communications:analyze
  → POST /api/v1/communications/analyze
  → optional analysis_id when history storage succeeds
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

Missing or invalid tokens return `401` with `WWW-Authenticate: Bearer`. A valid token without `communications:analyze` returns `403`. History routes reuse `communications:analyze`. Unknown and cross-user analysis resources return `404`, not `403`. History without `DATABASE_URL` returns `503`.

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
CommunicationAnalysisWorkflowService (app/application/services)
  ├── CommunicationAnalysisService → AIProvider
  └── AnalysisHistoryService → PostgreSQL repositories (when configured)
```

Routes validate the incoming request via Pydantic, resolve a workflow service through FastAPI dependencies, and return the result. Phase 10 added no connector HTTP endpoints; Gmail and Graph adapters are not reachable through this API surface. See [Endpoints](endpoints.md) for the concrete routes, [Persistence](../architecture/persistence.md) for ownership and failure semantics, and [Sequence Diagrams](../architecture/sequence-diagrams.md) for a step-by-step walkthrough.
