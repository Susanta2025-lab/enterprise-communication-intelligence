# ADR-003: FastAPI as the Web Framework

## Status

Accepted

## Date

Phase 1 (Foundation)

## Context

ECI Platform needs a Python web framework for its REST API that supports strong request/response validation, automatic API documentation, and async-capable request handling, while keeping route code thin so business logic can live in the application layer per ADR-001.

## Decision

Use FastAPI as the web framework for all HTTP concerns (`app/api/`, `app/main.py`).

## Alternatives Considered

- **Flask** — mature and simple, but has no built-in request/response validation or OpenAPI generation; both would need to be added via third-party extensions, increasing integration effort and reducing consistency with the Pydantic-based domain layer.
- **Django REST Framework** — capable, but brings a full-framework footprint (ORM, admin, settings system) that is unnecessary for a service with no database in this phase, and its serializer system would duplicate the validation already provided by Pydantic models.

## Consequences

- Request/response validation is expressed once, as Pydantic models, and reused directly as FastAPI route type hints — no separate serializer layer.
- OpenAPI documentation (`/docs`, `/openapi.json`) is generated automatically from route and model definitions, with no manual schema authoring (see `tests/integration/test_docs.py`).
- Dependency injection (`fastapi.Depends`) is used to resolve `AIProvider` and `CommunicationAnalysisService`, keeping route functions thin (see `app/api/routes/communications.py`).

## Benefits

- Native Pydantic v2 integration removes duplication between validation and API documentation.
- Async endpoint support is available for future I/O-bound provider calls (e.g. calling a cloud AI service), without requiring a framework migration.
- Built-in `TestClient` (Starlette-based) enables fast, dependency-free integration tests (`tests/integration/`).

## Trade-offs

- FastAPI's dependency-injection pattern (`Depends(...)` as a default argument) requires a Ruff `flake8-bugbear` allowlist entry (`extend-immutable-calls`) to avoid a false-positive `B008` lint error — a minor tooling accommodation, not a design compromise.
- The current route handlers are synchronous (`def`, not `async def`), matching the synchronous `MockAIProvider`; adopting `async def` will be revisited if/when a provider requires awaited I/O.

## Related Components

- `app/main.py`, `app/api/router.py`, `app/api/dependencies.py`, `app/api/routes/`
- [API Overview](../api/overview.md)
