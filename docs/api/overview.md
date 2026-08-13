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

FastAPI generates OpenAPI documentation automatically from the route definitions and Pydantic schemas:

- Swagger UI: `GET /docs`
- OpenAPI schema: `GET /openapi.json`

No manual OpenAPI authoring is required or performed; the schema reflects the current route and model definitions exactly.

## Authentication Status

**No authentication or authorization is implemented.** All endpoints are open. This is explicitly out of scope for the current phase (see `.cursor/rules/enterprise-communication-intelligence.mdc` and the Phase 5 roadmap entry) and should not be treated as production-ready without an authentication layer.

## Provider Status

The API resolves an `AIProvider` through configuration (`AI_PROVIDER`, default `mock`). Supported values are `mock` and `microsoft_foundry`. Automated tests and the default local configuration use `MockAIProvider`. See [Provider Abstraction](../architecture/provider-abstraction.md) and [Microsoft Foundry](../cloud/azure-ai-foundry.md).

## Request Flow (High Level)

```text
Client
  ↓ HTTP request
FastAPI route (app/api/routes/*)
  ↓ dependency injection
CommunicationAnalysisService (app/application/services)
  ↓ AIProvider interface (app/domain/interfaces)
MockAIProvider (app/providers/mock)
```

Routes validate the incoming request via Pydantic, resolve a `CommunicationAnalysisService` through FastAPI dependencies, delegate to `service.analyze(...)`, and return the result. See [Endpoints](endpoints.md) for the concrete routes and [Sequence Diagrams](../architecture/sequence-diagrams.md) for a step-by-step walkthrough.
