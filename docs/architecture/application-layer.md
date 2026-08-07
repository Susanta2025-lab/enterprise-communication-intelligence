# Application Layer

The application layer (`app/application/`) contains one implemented service as of Phase 5: `CommunicationAnalysisService` (`app/application/services/communication_analysis.py`).

## Role of `CommunicationAnalysisService`

The service is the single orchestration point between the API layer and the AI provider abstraction. It:

1. Receives an already-validated `CommunicationRequest` (validation happens in the Pydantic domain models before the service is ever called).
2. Delegates analysis to the injected `AIProvider`.
3. Returns the provider's `CommunicationAnalysisResult` unchanged on success.
4. Translates any provider exception into `AnalysisFailedError`.
5. Emits structured logs at each stage.

## Constructor Injection

```python
service = CommunicationAnalysisService(provider)
```

The service's `__init__` takes exactly one dependency — an `AIProvider` — and stores it as `self._provider`. It never constructs a provider itself and never imports `app.providers.factory`. The API layer (`app/api/dependencies.py`) is responsible for resolving the provider via the factory and passing it in.

## Orchestration Responsibility

`analyze(request: CommunicationRequest) -> CommunicationAnalysisResult` is the service's only public method. Its orchestration is intentionally linear:

```python
def analyze(self, request):
    logger.info("communication_analysis_started", ...)
    try:
        result = self._provider.analyze(request)
    except Exception as exc:
        logger.error("communication_analysis_failed", ...)
        raise AnalysisFailedError(...) from exc
    logger.info("communication_analysis_completed", ...)
    return result
```

There is no branching on provider type, no retry logic, and no additional business rules layered on top of the provider's output — the service trusts the domain models to have already validated the request, and trusts the provider to produce a valid `CommunicationAnalysisResult`.

## Provider Failure Translation

If `self._provider.analyze(request)` raises any exception, the service:

- Logs `communication_analysis_failed` with the provider's class name, the message ID (if present), and `str(exc)` — never the message body.
- Raises `AnalysisFailedError(f"AI provider '{provider_name}' failed to analyze the communication.")`, using `raise ... from exc` to preserve the original cause internally without exposing it externally.

This keeps the API layer's exception handling simple: it only needs to know about `ContextMeshError` and its subclasses, never about what a specific provider might raise.

## Structured Logging

Three structured log events are emitted, all via `app.core.logging.get_logger(__name__)`:

| Event | Level | Fields |
|---|---|---|
| `communication_analysis_started` | info | `provider`, `message_id`, `source_type` |
| `communication_analysis_completed` | info | `provider`, `message_id`, `priority`, `category` |
| `communication_analysis_failed` | error | `provider`, `message_id`, `error` |

None of these log the communication body, sender/recipient contents beyond what's already structural (message id), credentials, or secrets.

## Statelessness

`CommunicationAnalysisService` holds only a reference to its injected provider (`self._provider`); it has no other instance state. A single instance can safely handle repeated, unrelated `analyze()` calls — this is verified in `tests/unit/application/test_communication_analysis_service.py` (`test_service_remains_stateless_across_requests`).

## What the Service Deliberately Does Not Do

- **No HTTP work.** It never imports `fastapi`, builds a `Response`, or reads request headers.
- **No environment or configuration access.** It never calls `get_settings()` or reads an environment variable; provider selection happens entirely upstream, in `app/api/dependencies.py` and `app/providers/factory.py`.
- **No provider instantiation.** It never calls `create_ai_provider()` or imports a concrete provider class.
- **No persistence.** Results are not stored anywhere; the service is a pure request/response orchestrator.
