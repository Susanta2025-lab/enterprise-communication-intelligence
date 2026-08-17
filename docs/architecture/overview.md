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
MockAIProvider | MicrosoftFoundryProvider | AmazonBedrockProvider
```

Every layer in this path is implemented and exercised by tests spanning `tests/unit` and `tests/integration`. Automated tests stay offline; Microsoft Foundry and Amazon Bedrock are exercised through mocked SDK clients. Live ECI → Bedrock verification is complete.

## Purpose of Each Layer

- **FastAPI REST API (`app/api`)** — HTTP transport. Defines routes (`app/api/routes/`), the API router assembly (`app/api/router.py`), and dependency wiring (`app/api/dependencies.py`). Contains no business logic; every route validates input via Pydantic and delegates to a service.
- **Application service (`app/application`)** — Orchestrates use cases. `CommunicationAnalysisService` receives an already-validated `CommunicationRequest`, calls the injected `AIProvider`, translates provider failures into `AnalysisFailedError`, and emits structured logs. It has no knowledge of FastAPI, HTTP, or which concrete provider is behind the interface.
- **Domain (`app/domain`)** — Provider-independent business objects: enums (`SourceType`, `PriorityLevel`, `MessageCategory`), models (`CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`), schemas (`CommunicationRequest`, `CommunicationAnalysisResult`), and the `AIProvider` interface. Domain code imports neither FastAPI nor any cloud SDK.
- **Providers (`app/providers`)** — Concrete implementations of `AIProvider`. `MockAIProvider`, `MicrosoftFoundryProvider`, and `AmazonBedrockProvider` are implemented. The two real LLM adapters share `app/providers/common/`. `app/providers/factory.py` selects a provider from configuration.
- **Core (`app/core`)** — Cross-cutting concerns: `config.py` (Pydantic Settings), `logging.py` (structlog configuration), `exceptions.py` (the base application exception hierarchy). `app/core/security.py` exists as an empty scaffold file with no implementation.

## Provider Independence

The application service and every layer above it depend only on `app.domain.interfaces.AIProvider`, never on `MockAIProvider`, `MicrosoftFoundryProvider`, `AmazonBedrockProvider`, or any other concrete provider class. Provider selection happens in exactly one place — `app/providers/factory.py` — driven by the `AI_PROVIDER` setting. This means:

- Swapping providers requires no change to `CommunicationAnalysisService` or any route.
- Amazon Bedrock was added as `app/providers/amazon_bedrock/` plus one factory branch, without changing application or API code.

## Current Implementation Boundary

The system is fully synchronous and has no persistence or API-level authentication. When `AI_PROVIDER=mock`, there are no external network calls. When `AI_PROVIDER=microsoft_foundry`, inference goes to Microsoft Foundry using Entra ID. When `AI_PROVIDER=amazon_bedrock`, inference goes to Amazon Bedrock through Converse. Automated tests do not execute those cloud paths. Live ECI → Foundry and ECI → Bedrock verification is complete, including hosted Container Apps and Fargate paths.

## Future Extensibility

Production observability remains unimplemented (Phase 7). Additional providers can still be added behind `AIProvider` and the factory without changing the application or API layers. See [Provider Abstraction](provider-abstraction.md) and [`docs/cloud/`](../cloud/README.md).
