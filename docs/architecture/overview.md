# Architecture Overview

## Implemented Request Path

```text
Client
  ↓
FastAPI REST API        (app/api)
  ↓
CommunicationAnalysisService   (app/application/services)
  ↓
AIProvider interface    (app/domain/interfaces)
  ↓
MockAIProvider          (app/providers/mock)
```

Every layer in this path is implemented and exercised by tests (94 passing tests as of Phase 5, spanning `tests/unit` and `tests/integration`).

## Purpose of Each Layer

- **FastAPI REST API (`app/api`)** — HTTP transport. Defines routes (`app/api/routes/`), the API router assembly (`app/api/router.py`), and dependency wiring (`app/api/dependencies.py`). Contains no business logic; every route validates input via Pydantic and delegates to a service.
- **Application service (`app/application`)** — Orchestrates use cases. `CommunicationAnalysisService` receives an already-validated `CommunicationRequest`, calls the injected `AIProvider`, translates provider failures into `AnalysisFailedError`, and emits structured logs. It has no knowledge of FastAPI, HTTP, or which concrete provider is behind the interface.
- **Domain (`app/domain`)** — Provider-independent business objects: enums (`SourceType`, `PriorityLevel`, `MessageCategory`), models (`CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`), schemas (`CommunicationRequest`, `CommunicationAnalysisResult`), and the `AIProvider` interface. Domain code imports neither FastAPI nor any cloud SDK.
- **Providers (`app/providers`)** — Concrete implementations of `AIProvider`. Only `app/providers/mock/provider.py` (`MockAIProvider`) is implemented. `app/providers/factory.py` selects a provider from configuration. `app/providers/aws/` and `app/providers/azure/` exist only as empty scaffold packages with no implementation.
- **Core (`app/core`)** — Cross-cutting concerns: `config.py` (Pydantic Settings), `logging.py` (structlog configuration), `exceptions.py` (the base application exception hierarchy). `app/core/security.py` exists as an empty scaffold file with no implementation.

## Provider Independence

The application service and every layer above it depend only on `app.domain.interfaces.AIProvider`, never on `MockAIProvider` or any concrete provider class. Provider selection happens in exactly one place — `app/providers/factory.py` — driven by the `AI_PROVIDER` setting. This means:

- Swapping providers requires no change to `CommunicationAnalysisService` or any route.
- Adding a future Azure or AWS provider means adding a new module under `app/providers/` and one branch in the factory — not touching application or API code.

## Current Implementation Boundary

As of Phase 5, the system is fully synchronous, single-process, and has no persistence, authentication, or external network calls. The only "external" component conceptually represented is the `AIProvider`, and its only real implementation (`MockAIProvider`) is itself local and deterministic.

## Future Extensibility (Not Yet Implemented)

The architecture is structured so that Azure AI Foundry and Amazon Bedrock adapters can be added later behind the existing `AIProvider` interface, selected via `AI_PROVIDER`, without changing the application or API layers. This capability is a *design property* of the current code, not a delivered feature — no Azure or AWS provider code exists in the repository today. See [Provider Abstraction](provider-abstraction.md) and [`docs/cloud/`](../cloud/README.md).
