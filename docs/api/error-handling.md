# Error Handling

This describes the error handling actually implemented in `app/main.py`, `app/core/exceptions.py`, and `app/application/exceptions.py`.

## Validation Errors (Pydantic/FastAPI)

Requests that fail Pydantic model validation (e.g. empty `body`, invalid `source_type`, missing required fields, or unexpected fields — all domain models use `extra="forbid"`) are rejected by FastAPI's default `RequestValidationError` handling before any application code runs.

- **Status code:** `422 Unprocessable Entity`
- **Body shape:** FastAPI's default validation error format, an array of error objects under `"detail"`, each with `type`, `loc`, `msg`, and `input`.

This is FastAPI's built-in behavior; no custom validation error handler is registered in `app/main.py`.

## Application Exception Hierarchy

Defined in `app/core/exceptions.py`:

```python
class ContextMeshError(Exception):
    """Base error for all ContextMesh application failures."""

class ConfigurationError(ContextMeshError):
    """Raised when application configuration is invalid or incomplete."""

class ServiceUnavailableError(ContextMeshError):
    """Raised when a required service dependency is unavailable."""
```

`app/application/exceptions.py` adds one application-layer exception:

```python
class AnalysisFailedError(ContextMeshError):
    """Raised when an AI provider fails to analyze a communication."""
```

All of these carry a plain `.message: str` and no additional context, stack trace, or provider internals.

## Registered Exception Handlers (`app/main.py`)

Two handlers are registered on the FastAPI app:

| Exception type | Status code | Response body | Logged event |
|---|---|---|---|
| `ServiceUnavailableError` | `503` | `{"detail": exc.message}` | `service_unavailable` (warning) |
| `ContextMeshError` (and any subclass not more specifically registered) | `500` | `{"detail": exc.message}` | `application_error` (error) |

Because Starlette/FastAPI matches exception handlers by most-specific registered type, `ConfigurationError` and `AnalysisFailedError` — which have no dedicated handler — are both caught by the `ContextMeshError` handler and return `500`.

## Configuration Errors

If `AI_PROVIDER` is set to an unsupported value, `app/providers/factory.py` raises:

```text
ConfigurationError("Unsupported AI provider '<value>'. Supported providers: mock")
```

This is raised during dependency resolution (`get_ai_provider` in `app/api/dependencies.py`), before the route body executes, and is translated into a `500` response by the `ContextMeshError` handler. There is no silent fallback to another provider.

## Provider/Service Failures

If the injected `AIProvider.analyze(...)` call raises any exception, `CommunicationAnalysisService.analyze(...)` (`app/application/services/communication_analysis.py`):

1. Logs `communication_analysis_failed` with the provider name, message ID, and error message (never the message body).
2. Raises `AnalysisFailedError("AI provider '<ProviderClassName>' failed to analyze the communication.")`, chained via `raise ... from exc` so the original exception is preserved as the Python `__cause__` internally — it is not exposed in the HTTP response.

This is translated by the `ContextMeshError` handler into a `500` response.

## Safe Error-Response Behavior

- Responses only ever contain `{"detail": "<message>"}` for application exceptions — no stack traces, no exception class names, no provider SDK details.
- The `AnalysisFailedError` message includes only the provider's Python class name (e.g. `MockAIProvider`) and a generic failure statement, not the underlying exception's message or traceback.
- `ConfigurationError` messages mention the configured (invalid) provider name and the list of currently supported providers (`mock`) — this is intentional operator-facing feedback, not a security-sensitive detail, but it is documented here for completeness.

## Status Code Summary

| Status | Meaning | Source |
|---|---|---|
| `200` | Successful request | Normal route return |
| `422` | Request failed schema validation | FastAPI/Pydantic default behavior |
| `500` | Application or configuration error (`ContextMeshError` and subclasses, including `ConfigurationError`, `AnalysisFailedError`) | `app/main.py` exception handler |
| `503` | A required service dependency is unavailable (`ServiceUnavailableError`) | `app/main.py` exception handler; documented on `POST /api/v1/communications/analyze` in OpenAPI, but not currently raised by any implemented code path |

No other status codes are produced by application code in this phase.
