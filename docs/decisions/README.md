# Architecture Decision Records (ADRs)

## Purpose

ADRs capture significant architectural decisions for ContextMesh, along with the context and alternatives that were considered, so future contributors understand *why* the system is structured the way it is — not just what it currently looks like.

## Status Meanings

| Status | Meaning |
|---|---|
| `Accepted` | The decision is implemented and in effect in the current codebase |
| `Proposed` | The decision is documented but not yet implemented |
| `Superseded` | The decision has been replaced by a later ADR |

## Index

| ADR | Title | Status |
|---|---|---|
| [ADR-001](ADR-001-clean-architecture.md) | Clean Architecture Layering | Accepted |
| [ADR-002](ADR-002-provider-abstraction.md) | Provider Abstraction for AI Analysis | Accepted |
| [ADR-003](ADR-003-fastapi.md) | FastAPI as the Web Framework | Accepted |
| [ADR-004](ADR-004-pydantic-v2.md) | Pydantic v2 for Validation, Serialization, and Configuration | Accepted |
| [ADR-005](ADR-005-rest-api.md) | Synchronous REST API for Communication Analysis | Accepted |
| [ADR-006](ADR-006-azure-ai-foundry.md) | Azure AI Foundry Provider | *(placeholder — future decision, not yet made)* |
| [ADR-007](ADR-007-amazon-bedrock.md) | Amazon Bedrock Provider | *(placeholder — future decision, not yet made)* |

ADR-006 and ADR-007 remain unpopulated placeholders. Cloud provider adapters are a planned future capability (see [`docs/cloud/`](../cloud/README.md) and [`docs/roadmap/README.md`](../roadmap/README.md)); no Azure or AWS integration decision has been finalized or implemented yet.

## Template

Use [`ADR-template.md`](ADR-template.md) as the starting point for any new ADR.
