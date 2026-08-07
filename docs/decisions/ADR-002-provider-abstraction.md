# ADR-002: Provider Abstraction for AI Analysis

## Status

Accepted

## Date

Phase 3 (Provider Abstraction)

## Context

Communication analysis must eventually be backed by real AI services (Azure AI Foundry, Amazon Bedrock), but the MVP needs a deterministic, offline, credential-free way to develop and test against before any cloud provider is integrated. The application and API layers should not need to change when a cloud provider is added or swapped.

## Decision

Introduce a single abstract interface, `AIProvider` (`app/domain/interfaces/ai_provider.py`), with one method, `analyze(request: CommunicationRequest) -> CommunicationAnalysisResult`. Implement `MockAIProvider` (`app/providers/mock/provider.py`) as the first and currently only concrete provider. Select the active provider via a factory function, `create_ai_provider()` (`app/providers/factory.py`), driven entirely by the `AI_PROVIDER` configuration value. Wire the factory into FastAPI via dependency injection (`app/api/dependencies.py`), never by instantiating a provider directly in a route or service.

## Alternatives Considered

- **Provider conditionals in services** — `CommunicationAnalysisService` checks `if provider_name == "mock": ... elif provider_name == "azure": ...`. Rejected: this would put provider-specific branching inside business orchestration code, violating the project's dependency-direction rule and making the service harder to test and extend.
- **Direct SDK calls from routes** — routes import and call a cloud SDK directly. Rejected: this would couple the HTTP layer to a specific cloud vendor and make the mock/local development path impossible without conditionally disabling entire code paths.

## Consequences

- `CommunicationAnalysisService` and every route depend only on `AIProvider`, never on `MockAIProvider` or any future concrete class.
- Adding a new provider requires: (1) a new module implementing `AIProvider`, (2) one new branch in `create_ai_provider`. No other code changes.
- Misconfiguration (an unsupported `AI_PROVIDER` value) fails explicitly with `ConfigurationError` rather than silently falling back to the mock provider.

## Benefits

- The entire request/response path can be developed and tested (94 passing tests) without any cloud credentials or network access.
- Provider selection is centralized in one function, making it easy to audit and reason about.
- No provider-specific business logic exists outside `app/providers/`.

## Trade-offs

- The abstraction currently has only one real implementation, so its value (swappability) is not yet exercised by a second provider — this is accepted as forward-looking infrastructure, not speculative business logic, since it directly supports the stated multi-channel/multi-provider roadmap.
- `AIProvider.analyze()` is synchronous; if a future cloud provider requires async I/O, either the interface will need to change or providers will need to bridge sync/async internally.

## Related Components

- `app/domain/interfaces/ai_provider.py`, `app/providers/mock/provider.py`, `app/providers/factory.py`, `app/api/dependencies.py`
- [Provider Abstraction](../architecture/provider-abstraction.md)
- ADR-001 (Clean Architecture Layering)
