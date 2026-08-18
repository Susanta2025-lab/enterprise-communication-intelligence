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
class ECIPlatformError(Exception):
    """Base error for all ECI Platform application failures."""

class ConfigurationError(ECIPlatformError):
    """Raised when application configuration is invalid or incomplete."""

class ServiceUnavailableError(ECIPlatformError):
    """Raised when a required service dependency is unavailable."""
```

`app/application/exceptions.py` adds one application-layer exception:

```python
class AnalysisFailedError(ECIPlatformError):
    """Raised when an AI provider fails to analyze a communication."""
```

All of these carry a plain `.message: str` and no additional context, stack trace, or provider internals.

## Registered Exception Handlers (`app/main.py`)

Two handlers are registered on the FastAPI app:

| Exception type | Status code | Response body | Logged event |
|---|---|---|---|
| `ServiceUnavailableError` | `503` | `{"detail": exc.message}` | `service_unavailable` (warning) |
| `ECIPlatformError` (and any subclass not more specifically registered) | `500` | `{"detail": exc.message}` | `application_error` (error) |

Because Starlette/FastAPI matches exception handlers by most-specific registered type, `ConfigurationError` and `AnalysisFailedError` — which have no dedicated handler — are both caught by the `ECIPlatformError` handler and return `500`.

Authentication and authorization failures are raised as FastAPI `HTTPException` values from `app/api/dependencies.py`. They are not `ECIPlatformError` subclasses and therefore are not mapped to `500`.

## Authentication and Authorization Errors

When `AUTH_MODE=oidc`, `POST /api/v1/communications/analyze` requires a bearer token. Responses:

| Condition | Status | `WWW-Authenticate` | Body |
|---|---|---|---|
| Missing bearer token | `401` | `Bearer` | `{"detail": "Not authenticated"}` |
| Invalid, expired, wrong issuer/audience, or bad signature | `401` | `Bearer` | `{"detail": "Not authenticated"}` |
| Valid token without `communications:analyze` | `403` | not set | `{"detail": "Not authorized"}` |

Bounded failure reasons are written to structured logs only (`missing_token`, `invalid_token`, `expired_token`, `invalid_issuer`, `invalid_audience`, `unknown_signing_key`, `insufficient_permission`). JWT library exception text is not returned or logged.

## Configuration Errors

If `AI_PROVIDER` is set to an unsupported value, `app/providers/factory.py` raises:

```text
ConfigurationError("Unsupported AI provider '<value>'. Supported providers: mock, microsoft_foundry, amazon_bedrock")
```

This is raised during dependency resolution (`get_ai_provider` in `app/api/dependencies.py`), before the route body executes, and is translated into a `500` response by the `ECIPlatformError` handler. There is no silent fallback to another provider.

## Provider/Service Failures

If the injected `AIProvider.analyze(...)` call raises any exception, `CommunicationAnalysisService.analyze(...)` (`app/application/services/communication_analysis.py`):

1. Logs `communication_analysis_failed` with the provider name, message ID, `duration_ms`, and `error_class` (never the message body or `str(exc)`).
2. Raises `AnalysisFailedError("AI provider '<ProviderClassName>' failed to analyze the communication.")`, chained via `raise ... from exc` so the original exception is preserved as the Python `__cause__` internally — it is not exposed in the HTTP response.

The HTTP `detail` still uses the provider's Python class name (for example `MockAIProvider`). Operational logs use the configuration provider name and `error_class`.

This is translated by the `ECIPlatformError` handler into a `500` response.

## Safe Error-Response Behavior

- Responses only ever contain `{"detail": "<message>"}` for application exceptions — no stack traces, no exception class names, no provider SDK details.
- The `AnalysisFailedError` message includes only the provider's Python class name (e.g. `MockAIProvider`) and a generic failure statement, not the underlying exception's message or traceback.
- `ConfigurationError` messages mention the configured (invalid) provider name and the list of currently supported providers (`mock`, `microsoft_foundry`) — this is intentional operator-facing feedback, not a security-sensitive detail, but it is documented here for completeness.

## Status Code Summary

| Status | Meaning | Source |
|---|---|---|
| `200` | Successful request | Normal route return |
| `401` | Missing or invalid bearer token | `require_communications_analyze` when `AUTH_MODE=oidc` |
| `403` | Authenticated token lacks `communications:analyze` | `require_communications_analyze` when `AUTH_MODE=oidc` |
| `422` | Request failed schema validation | FastAPI/Pydantic default behavior |
| `500` | Application or configuration error (`ECIPlatformError` and subclasses, including `ConfigurationError`, `AnalysisFailedError`) | `app/main.py` exception handler |
| `503` | A required service dependency is unavailable (`ServiceUnavailableError`) | `app/main.py` exception handler; documented on `POST /api/v1/communications/analyze` in OpenAPI, but not currently raised by any implemented code path |
