# Phase 02 Domain Model

## Objective

Establish a provider-independent communication domain that defines the core business objects, enums, schemas, and AI provider interface shared by future Azure AI Foundry, AWS Bedrock, and other backends.

## Business Value

- Creates a stable, channel-neutral vocabulary for communication intelligence.
- Prevents Azure, AWS, FastAPI, and transport concerns from leaking into business models.
- Enables later provider implementations and APIs to share one validated domain contract.

## Deliverables

- Domain enums: `SourceType`, `PriorityLevel`, `MessageCategory`
- Domain models: `CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`
- Domain schemas: `CommunicationRequest`, `CommunicationAnalysisResult`
- Domain interface: `AIProvider`
- Unit tests for validation, enums, schemas, serialization, and the provider contract
- Roadmap status update for Phase 2

## Tasks

- [x] Define channel-neutral domain enums
- [x] Implement core communication domain models with Pydantic v2 validation
- [x] Implement domain input/output schemas for analysis
- [x] Define the provider-independent `AIProvider` interface
- [x] Add deterministic unit tests for models, enums, schemas, and interfaces
- [x] Update roadmap documentation for Phase 2 completion

## Architectural Decisions

- Keep `app/domain/` free of FastAPI, HTTP, Azure SDK, and AWS SDK dependencies.
- Place domain code in the existing scaffold packages (`models/`, `schemas/`, `interfaces/`) rather than introducing a parallel flat-module layout.
- Use Pydantic v2 models as the domain representation to provide validation and serialization without introducing a separate ORM or DTO stack.
- Model communications as channel-neutral messages with `SourceType`, rather than email-specific entities.
- Represent analysis outputs as composed value objects (`Summary`, `Priority`, `ActionItem`, `DraftReply`) under `CommunicationAnalysis`.
- Define `AIProvider` as an abstract interface that accepts `CommunicationRequest` and returns `CommunicationAnalysisResult`, with no vendor-specific types.
- Reject empty or whitespace-only required text fields at the domain boundary.
- Leave `app/domain/services/` untouched in this phase; no application-service layer was introduced yet.

## Acceptance Criteria

- [x] Domain models exist for message, metadata, analysis, summary, priority, action items, and draft replies
- [x] Strongly typed enums exist for source type, priority level, and message category
- [x] Domain schemas exist for analysis request and result payloads
- [x] `AIProvider` interface is defined without provider implementations
- [x] Invalid bodies, source types, priorities, and missing required metadata fail validation
- [x] Unit tests cover validation, enum behavior, schema usage, and serialization round-trips
- [x] Domain layer has no FastAPI or cloud SDK dependency
- [x] `python -m pip check`, `python -m ruff check .`, and `python -m pytest` succeed

## Verification Results

- `python -m pip check`: passed (`No broken requirements found.`)
- `python -m ruff check .`: passed (`All checks passed!`)
- `python -m pytest`: passed (`51 passed, 1 warning`)

## Risks and Trade-offs

- Including future channel values in `SourceType` now improves extensibility, but those channels have no adapters yet.
- Using Pydantic models in the domain couples business objects to a validation library; this is accepted for MVP consistency with the rest of the stack.
- The `AIProvider` interface is synchronous in this phase; async adaptations can be considered when real I/O providers are implemented.

## Lessons Learned

- Channel-neutral naming (`CommunicationMessage`, `SourceType`, `sender`, `recipients`) keeps email as one source type instead of the center of the model.
- Nested Pydantic validation naturally enforces request integrity before any provider or API layer is introduced.
- A tiny stub provider in tests is enough to lock the interface contract without implementing Phase 3.

## Remaining Limitations

- No provider factory or concrete AI providers are implemented.
- No REST endpoints expose the domain models yet.
- No persistence, authentication, or application-service orchestration is included.
- Draft-reply and action-item generation behavior is modeled only, not executed.

## Next Phase

Phase 3 – Provider Abstraction: introduce provider selection/factory patterns and concrete provider adapters behind the `AIProvider` interface, still without leaking vendor concerns into the domain.
