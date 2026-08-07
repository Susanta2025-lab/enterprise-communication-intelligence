# Phase 04 AI Services

## Objective

Implement the application service layer that orchestrates communication analysis: validating requests through existing domain models, invoking an injected `AIProvider`, translating provider failures into application exceptions, and emitting structured logs — without any provider-specific logic.

## Business Value

- Provides a single, stable orchestration point for communication analysis that later API routes can depend on.
- Keeps business orchestration completely decoupled from Azure, AWS, or the mock provider.
- Ensures provider failures surface as consistent application exceptions instead of raw provider errors.
- Establishes constructor-based dependency injection as the pattern for wiring providers into services.

## Deliverables

- `app/application/exceptions.py` with `AnalysisFailedError`
- `app/application/services/communication_analysis.py` with `CommunicationAnalysisService`
- Unit tests covering orchestration, injection, failure translation, validation, and determinism
- Roadmap updates for Phase 4 completion

## Architecture

```text
API
  ↓
Application Service (CommunicationAnalysisService)
  ↓
AIProvider Interface (domain)
  ↑
MockAIProvider (providers.mock)
```

- `CommunicationAnalysisService` depends only on `app.domain.interfaces.AIProvider`, `app.domain.schemas`, and `app.core.logging`.
- It does not import FastAPI, the provider factory, or any concrete provider.
- The provider factory (`app/providers/factory.py`) and its use remain in the API dependency layer (`app/api/dependencies.py`), unchanged in this phase.

## Service Responsibilities

`CommunicationAnalysisService`:

- Receives a `CommunicationRequest` (already validated by Pydantic domain models).
- Logs `communication_analysis_started` with provider name, message id, and source type (no message bodies or secrets).
- Calls `provider.analyze(request)` on the constructor-injected `AIProvider`.
- On success, logs `communication_analysis_completed` with priority/category and returns the `CommunicationAnalysisResult` unchanged.
- On provider failure, logs `communication_analysis_failed` with the error message only, then raises `AnalysisFailedError` chained to the original exception.
- Holds no mutable state between calls; a single instance can safely handle multiple sequential requests.

## Dependency Flow

- The service is constructed with `CommunicationAnalysisService(provider)`, where `provider` is any `AIProvider` implementation.
- The service never constructs a provider and never calls `create_ai_provider()`.
- Provider selection and construction remain the responsibility of the API dependency layer (Phase 3), to be wired to the service in a later REST phase.

## Architectural Decisions

- Added `AnalysisFailedError` in `app/application/exceptions.py`, subclassing the existing `ECIPlatformError`, since no existing exception represented "provider failed during orchestration."
- Kept `app/core/exceptions.py` unchanged; application-layer exceptions live separately from core exceptions per the requested structure.
- Used a narrow `except Exception` solely to translate provider failures into `AnalysisFailedError` at the orchestration boundary, re-raising with `raise ... from exc` to preserve the original cause without leaking it to callers.
- Used structured logging (`app.core.logging.get_logger`) with only non-sensitive fields (provider name, message id, source type, priority, category); message bodies and credentials are never logged.
- Did not read configuration or environment variables in the service; provider selection stays in the API/factory layer.

## Acceptance Criteria

- [x] `CommunicationAnalysisService` validates via existing domain models, delegates to an injected `AIProvider`, and returns `CommunicationAnalysisResult`
- [x] Constructor injection only; no provider instantiation or factory calls inside the service
- [x] Provider exceptions are translated into `AnalysisFailedError`
- [x] Structured logs emitted for start, completion, and failure without sensitive data
- [x] Service has no FastAPI, HTTP, environment, or configuration dependency
- [x] Unit tests cover successful orchestration, provider invocation, dependency injection, provider failure, invalid request, and deterministic behavior
- [x] All existing tests continue to pass
- [x] `python -m pip check`, `python -m ruff check .`, and `python -m pytest` succeed

## Verification Results

- `python -m pip check`: passed (`No broken requirements found.`)
- `python -m ruff check .`: passed (`All checks passed!`)
- `python -m pytest`: passed (`81 passed, 1 warning`), including the new application service suite

## Remaining Limitations

- No REST endpoint exposes `CommunicationAnalysisService` yet.
- No wiring exists yet between `app/api/dependencies.py` and the new service (planned for the REST API phase).
- Only the mock provider has been exercised against the service; Azure and AWS providers do not exist yet.

## Lessons Learned

- Constructor injection keeps the service trivially testable with simple stub `AIProvider` implementations, with no mocking framework required.
- Translating provider exceptions at a single orchestration boundary keeps error handling consistent regardless of which provider is injected.
- Logging only structural metadata (ids, enum values) is sufficient for observability without risking sensitive data exposure.

## Next Phase

Phase 5 – REST API: expose `CommunicationAnalysisService` through a versioned REST endpoint, wiring the existing provider factory and dependency function to the service via FastAPI dependency injection.
