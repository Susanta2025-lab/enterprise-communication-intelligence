# ADR-004: Pydantic v2 for Validation, Serialization, and Configuration

## Status

Accepted

## Date

Phase 1–2 (Foundation, Domain Model)

## Context

ECI Platform needs consistent validation for domain models (`CommunicationMessage`, `CommunicationAnalysis`, etc.), for API request/response bodies, and for application configuration loaded from environment variables — ideally using one library so behavior (error format, type coercion) is consistent across all three.

## Decision

Use Pydantic v2 (`BaseModel`) for all domain models and schemas, and Pydantic Settings (`BaseSettings`) for configuration (`app/core/config.py`). Apply `model_config = ConfigDict(extra="forbid")` on every domain model to reject unrecognized fields, and use `field_validator` for custom rules such as rejecting blank strings (`app/domain/models/validation.py`).

## Alternatives Considered

- **Dataclasses** — lightweight, but provide no built-in validation, coercion, or JSON Schema generation; validation logic would need to be hand-written and would not integrate with FastAPI's automatic OpenAPI generation.
- **Manual validation** — full control, but duplicates logic across configuration and every API model, is error-prone, and produces inconsistent error messages.
- **Separate configuration library** (e.g. plain `os.environ` reads, or a different settings framework) — would decouple configuration validation from the rest of the codebase's validation approach, and lose the type coercion Pydantic Settings already provides.

## Consequences

- Every domain model doubles as its own JSON Schema source for OpenAPI, with no separate serializer definitions (see `tests/integration/test_docs.py`).
- Configuration values (`Settings`) are validated once at startup via the same library used for request bodies, giving consistent error behavior.
- `extra="forbid"` means malformed or unexpected client payloads are rejected outright (`422`) rather than silently ignored — verified in `tests/integration/test_communications.py` (e.g. `test_analyze_rejects_unknown_fields`).

## Benefits

- Single validation library across domain models, API schemas, and configuration reduces cognitive overhead and duplicated logic.
- Pydantic v2's performance improvements (over v1) and native FastAPI support avoid additional adapter code.
- `pydantic-settings` handles `.env` file loading, case-insensitive environment variable matching, and type coercion (e.g. `APP_PORT` as `int`) without custom parsing code.

## Trade-offs

- Pydantic's validation error format (`RequestValidationError`, nested `loc`/`msg`/`type` structures) is somewhat verbose for API consumers; this is accepted as FastAPI's standard behavior rather than building a custom formatter.
- `extra="forbid"` is stricter than the default `extra="ignore"`; it requires every domain model to be updated in lockstep with any deliberate schema change, rather than tolerating drift silently.

## Related Components

- `app/core/config.py`, `app/domain/models/`, `app/domain/schemas/`, `app/domain/models/validation.py`
- [Request/Response Models](../api/request-response-models.md)
