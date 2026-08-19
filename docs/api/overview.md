# API Overview

## Purpose

ECI Platform exposes a REST API for analyzing business communications: producing a summary, priority classification, category, action items, and an optional draft reply. Analysis is performed by a configurable `AIProvider` behind the scenes (see [Provider Abstraction](../architecture/provider-abstraction.md)).

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

```text
Client
  → Authorization: Bearer <JWT>
  → ECI validates signature, issuer, audience, and expiry
  → ECI requires permission communications:analyze
  → POST /api/v1/communications/analyze
```

Configuration (`app/core/config.py`):

- `AUTH_MODE=disabled` — allowed in development and tests; analyze does not require a token
- `AUTH_MODE=oidc` — requires `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`
- `APP_ENV=production` requires `AUTH_MODE=oidc` (fail closed)

This is **not** cloud workload identity. Foundry Managed Identity and the ECS Task Role authenticate ECI to AI platforms; they do not authenticate API callers.

Public (no token):

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/readiness`

Protected when `AUTH_MODE=oidc`:

- `POST /api/v1/communications/analyze`

Missing or invalid tokens return `401` with `WWW-Authenticate: Bearer`. A valid token without `communications:analyze` returns `403`.

Permissions are read only from bounded claims `scp`, `scope`, or `roles`. There is no user database or session store.

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
CommunicationAnalysisService (app/application/services)
  ↓ AIProvider interface (app/domain/interfaces)
MockAIProvider | MicrosoftFoundryProvider | AmazonBedrockProvider
```

Routes validate the incoming request via Pydantic, resolve a `CommunicationAnalysisService` through FastAPI dependencies, delegate to `service.analyze(...)`, and return the result. See [Endpoints](endpoints.md) for the concrete routes and [Sequence Diagrams](../architecture/sequence-diagrams.md) for a step-by-step walkthrough.
