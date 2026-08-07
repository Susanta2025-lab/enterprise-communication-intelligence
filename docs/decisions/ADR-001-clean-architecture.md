# ADR-001: Clean Architecture Layering

## Status

Accepted

## Date

Phase 1 (Foundation)

## Context

ContextMesh must eventually support multiple communication channels (Gmail, Outlook, Teams, Slack, WhatsApp, CRM/ERP systems, document repositories, calendars) and multiple AI providers (starting with a local mock, later Azure AI Foundry and Amazon Bedrock). A single-layer application would tightly couple business logic to FastAPI and to whichever provider was implemented first, making it expensive to add channels or providers later, and hard to test business logic without spinning up the web framework.

## Decision

Separate the codebase into four layers with a strict, one-directional dependency flow:

```text
API  →  Application  →  Domain  ←  Providers
```

- **`app/domain`** — provider-independent models, schemas, enums, and interfaces (`AIProvider`). No dependency on FastAPI or any cloud SDK.
- **`app/application`** — use-case orchestration (`CommunicationAnalysisService`). Depends on domain interfaces only.
- **`app/providers`** — concrete implementations of domain interfaces (`MockAIProvider` today; Azure/AWS adapters reserved as scaffolds).
- **`app/api`** — FastAPI routes and dependency wiring; depends on application and domain, never directly on a concrete provider.
- **`app/core`** — cross-cutting configuration, logging, and the base exception hierarchy, used by every layer but depending on none of them.

## Alternatives Considered

- **Single-layer FastAPI application** — routes directly implementing business logic and calling a provider inline. Rejected: business logic becomes untestable without an HTTP client, and every provider change requires touching route code.
- **Direct route-to-provider calls** (skip the application layer) — routes call `AIProvider` implementations directly. Rejected: there would be no single place to apply cross-cutting orchestration concerns (logging, failure translation) consistently across future use cases, and routes would need to know how to construct providers.

## Consequences

- Adding a new use case means adding a new application service, not modifying existing ones.
- Adding a new provider means adding a new module under `app/providers/`, not touching `app/application` or `app/api`.
- Domain code can be unit tested with plain Python objects, with no FastAPI or provider setup required.

## Benefits

- Business logic (`app/application`, `app/domain`) is testable in isolation (see `tests/unit/domain`, `tests/unit/application` — no HTTP, no credentials).
- Future channel and provider additions are additive, not invasive.
- Matches the project's explicit dependency-direction rule in `.cursor/rules/contextmesh.mdc`.

## Trade-offs

- More files and packages than a single-module application would require, for a currently small feature set (one use case, one provider).
- Contributors must understand the layering convention before adding code, or risk introducing a forbidden dependency (e.g. importing FastAPI inside `app/domain`).

## Related Components

- `app/domain/`, `app/application/`, `app/providers/`, `app/api/`, `app/core/`
- [Clean Architecture](../architecture/clean-architecture.md)
- [Dependency Flow](../architecture/dependency-flow.md)
