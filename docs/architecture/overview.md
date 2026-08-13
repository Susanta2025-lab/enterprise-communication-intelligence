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
MockAIProvider | MicrosoftFoundryProvider
```

Every layer in this path is implemented and exercised by tests spanning `tests/unit` and `tests/integration`. Automated tests stay offline; Microsoft Foundry is exercised through mocked SDK clients.

## Purpose of Each Layer

- **FastAPI REST API (`app/api`)** — HTTP transport. Defines routes (`app/api/routes/`), the API router assembly (`app/api/router.py`), and dependency wiring (`app/api/dependencies.py`). Contains no business logic; every route validates input via Pydantic and delegates to a service.
- **Application service (`app/application`)** — Orchestrates use cases. `CommunicationAnalysisService` receives an already-validated `CommunicationRequest`, calls the injected `AIProvider`, translates provider failures into `AnalysisFailedError`, and emits structured logs. It has no knowledge of FastAPI, HTTP, or which concrete provider is behind the interface.
- **Domain (`app/domain`)** — Provider-independent business objects: enums (`SourceType`, `PriorityLevel`, `MessageCategory`), models (`CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`), schemas (`CommunicationRequest`, `CommunicationAnalysisResult`), and the `AIProvider` interface. Domain code imports neither FastAPI nor any cloud SDK.
- **Providers (`app/providers`)** — Concrete implementations of `AIProvider`. `MockAIProvider` and `MicrosoftFoundryProvider` are implemented. `app/providers/factory.py` selects a provider from configuration.
- **Core (`app/core`)** — Cross-cutting concerns: `config.py` (Pydantic Settings), `logging.py` (structlog configuration), `exceptions.py` (the base application exception hierarchy). `app/core/security.py` exists as an empty scaffold file with no implementation.

## Provider Independence

The application service and every layer above it depend only on `app.domain.interfaces.AIProvider`, never on `MockAIProvider`, `MicrosoftFoundryProvider`, or any concrete provider class. Provider selection happens in exactly one place — `app/providers/factory.py` — driven by the `AI_PROVIDER` setting. This means:

- Swapping providers requires no change to `CommunicationAnalysisService` or any route.
- Adding a future Amazon Bedrock provider means adding a new module under `app/providers/` and one branch in the factory — not touching application or API code.

## Current Implementation Boundary

The system is fully synchronous and has no persistence or API-level authentication. When `AI_PROVIDER=mock`, there are no external network calls. When `AI_PROVIDER=microsoft_foundry`, inference goes to Microsoft Foundry using Entra ID; that path is not executed by the automated test suite.

## Future Extensibility

Amazon Bedrock, cloud hosting, and observability remain unimplemented. They can be added behind the existing `AIProvider` interface and factory without changing the application or API layers. See [Provider Abstraction](provider-abstraction.md) and [`docs/cloud/`](../cloud/README.md).
