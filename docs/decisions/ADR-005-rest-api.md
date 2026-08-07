# ADR-005: Synchronous REST API for Communication Analysis

## Status

Accepted

## Date

Phase 5 (REST API)

## Context

The `CommunicationAnalysisService` (Phase 4) needed to be exposed to external callers. The API needed to fit the existing layered architecture (ADR-001) without introducing new infrastructure (message queues, GraphQL servers) before there is a demonstrated need for them.

## Decision

Expose communication analysis as a single synchronous REST endpoint, `POST /api/v1/communications/analyze`, under the existing versioned API router (`app/api/router.py`). The route:

- Accepts and returns the same domain schemas used internally (`CommunicationRequest`, `CommunicationAnalysisResult`) — no separate "API DTO" layer.
- Resolves `CommunicationAnalysisService` via FastAPI dependency injection (`app/api/dependencies.py`), keeping the route function to request logging plus a single delegating call.
- Relies on the existing `ContextMeshError`/`ServiceUnavailableError` exception handlers (registered in `app/main.py`) for error translation, rather than adding endpoint-specific error handling.
- Documents `500` and `503` responses via an `ErrorResponse` model (`app/schemas/errors.py`) so OpenAPI reflects real failure modes.

## Alternatives Considered

- **GraphQL** — would allow flexible field selection, but adds a new dependency and query language for a service with exactly one operation today; rejected as premature given the current single-use-case scope.
- **Message queues** (async job submission + polling/webhook for results) — appropriate for long-running or high-throughput analysis, but the mock provider (and any near-term AI provider call) completes well within a normal HTTP request/response cycle; rejected until latency or throughput requirements justify the added operational complexity.
- **Direct SDK/library usage** (no HTTP API at all; consumers import `CommunicationAnalysisService` directly) — works only for same-process/same-language consumers and would not support the platform's stated goal of serving multiple channels and integrations over the network.

## Consequences

- The route module (`app/api/routes/communications.py`) contains no business logic — it is fully covered by delegating to `CommunicationAnalysisService`.
- Callers get a single, predictable request/response cycle; there is no polling, callback, or streaming protocol to implement or document.
- Because the domain schemas are reused directly as the API contract, any future domain schema change is automatically reflected in the OpenAPI schema and this documentation set — but also means domain and API concerns are not decoupled behind a separate versioned DTO layer.

## Benefits

- Versioning is handled once, centrally, via `Settings.api_v1_prefix`, not hard-coded per route.
- Thin routes make the HTTP layer easy to test (`tests/integration/test_communications.py`) independent of business-logic correctness (which is tested separately in `tests/unit/application`).
- Reusing domain schemas as API schemas avoids duplicate model definitions and keeps `docs/api/request-response-models.md` accurate to the actual code.

## Trade-offs

- No pagination, batching, or streaming — one request analyzes exactly one communication. Bulk analysis would require either a new endpoint or client-side looping.
- No authentication, rate limiting, or persistence of requests/results in this phase — the endpoint is only as safe as its deployment environment makes it.
- Reusing domain schemas as the wire format means any future domain-model evolution driven by cloud provider needs (Azure/AWS) will directly affect the public API contract, requiring careful, explicit versioning decisions rather than an insulating DTO layer.

## Related Components

- `app/api/routes/communications.py`, `app/api/router.py`, `app/api/dependencies.py`, `app/schemas/errors.py`
- [Endpoints](../api/endpoints.md), [Error Handling](../api/error-handling.md)
- ADR-001 (Clean Architecture Layering), ADR-002 (Provider Abstraction)
