# Phase 03 Provider Abstraction

## Objective

Create a configuration-driven provider abstraction layer with a deterministic mock AI provider, a factory for provider selection, and a FastAPI dependency hook so later services and routes can remain provider-independent.

## Business Value

- Lets local development and tests exercise communication analysis without cloud credentials or network access.
- Keeps Azure and AWS replaceable behind the existing `AIProvider` interface.
- Ensures unsupported provider configuration fails explicitly instead of silently falling back.
- Prepares the API layer for dependency-injected provider resolution.

## Deliverables

- `MockAIProvider` implementing `AIProvider`
- `create_ai_provider()` factory driven by `AI_PROVIDER`
- `get_ai_provider()` FastAPI dependency in `app/api/dependencies.py`
- Unit tests for mock provider, factory, and dependency resolution
- Roadmap updates for Phase 3 completion

## Tasks

- [x] Implement deterministic `MockAIProvider`
- [x] Implement configuration-driven provider factory
- [x] Add FastAPI dependency function for AI provider resolution
- [x] Normalize `AI_PROVIDER` values in settings
- [x] Add unit tests for mock provider, factory, and dependency behavior
- [x] Update roadmap documentation for Phase 3

## Architecture

```text
API dependency (get_ai_provider)
        ↓
Provider factory (create_ai_provider)
        ↓
AIProvider interface (domain)
        ↑
MockAIProvider (providers.mock)
```

- Only the mock provider is implemented in this phase.
- Azure and AWS remain future adapters under the existing empty scaffold packages.
- Unsupported providers fail explicitly with `ConfigurationError`.
- Provider selection is configuration-driven through `AI_PROVIDER`.
- The domain remains cloud-independent and does not import provider packages.

## Architectural Decisions

- Reuse the Phase 2 `AIProvider` interface; do not introduce a second provider base class.
- Keep provider-specific imports localized inside the factory (`mock` only for now).
- Raise the existing `ConfigurationError` for unsupported provider names; no new exception type was needed.
- Keep mock analysis rules intentionally simple and deterministic for test infrastructure.
- Expose provider creation through `get_ai_provider()` without introducing a DI framework or service locator.
- Normalize `AI_PROVIDER` to lowercase in settings so `MOCK` and `mock` resolve consistently.

## Acceptance Criteria

- [x] `MockAIProvider` conforms to `AIProvider` and returns valid `CommunicationAnalysisResult`
- [x] Mock output is deterministic and offline
- [x] Factory selects mock from configuration
- [x] Unsupported providers raise `ConfigurationError` with no silent fallback
- [x] Dependency function returns an `AIProvider` using configured selection
- [x] Existing health and docs endpoints remain unaffected
- [x] `python -m pip check`, `python -m ruff check .`, and `python -m pytest` succeed

## Verification Results

- `python -m pip check`: passed (`No broken requirements found.`)
- `python -m ruff check .`: passed (`All checks passed!`)
- `python -m pytest`: passed (`74 passed, 1 warning`)
- Existing health and documentation endpoint tests continued to pass

## Risks and Trade-offs

- Keyword heuristics in the mock provider are intentionally shallow and will diverge from real model behavior.
- Leaving Azure/AWS scaffold packages empty can look incomplete, but avoids speculative cloud code in this phase.
- Factory currently supports only `mock`; extending it later requires explicit new branches/imports.

## Remaining Limitations

- No Azure AI Foundry provider
- No AWS Bedrock provider
- No application analysis service
- No REST analysis endpoints
- No credential or cloud-specific settings

## Lessons Learned

- Localizing provider imports in the factory keeps optional cloud dependencies out of the import graph.
- Explicit unsupported-provider errors are clearer than defaulting to mock during early development.
- A tiny deterministic mock is enough to unlock later service and API work without cloud coupling.

## Next Phase

Phase 4 – AI Services: introduce application-level communication analysis orchestration that depends on `AIProvider` rather than concrete providers.
