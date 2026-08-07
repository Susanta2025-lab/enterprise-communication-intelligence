# ECI Platform Architecture Documentation

This directory documents the architecture implemented through **Phase 5 – REST API**.

## Contents

- [Overview](overview.md) — the implemented layered architecture end to end
- [Clean Architecture](clean-architecture.md) — how dependency direction and layering are applied
- [Dependency Flow](dependency-flow.md) — allowed and forbidden imports between layers
- [Application Layer](application-layer.md) — `CommunicationAnalysisService` responsibilities
- [Provider Abstraction](provider-abstraction.md) — `AIProvider`, `MockAIProvider`, and the provider factory
- [Project Structure](project-structure.md) — the actual repository layout and the role of each package
- [Sequence Diagrams](sequence-diagrams.md) — request-level walkthroughs

## Diagrams

Mermaid source files live in [`docs/diagrams/`](../diagrams/README.md):

- [`architecture.mmd`](../diagrams/architecture.mmd) — layered system diagram
- [`request-flow.mmd`](../diagrams/request-flow.mmd) — successful and failure request sequences
- [`provider-abstraction.mmd`](../diagrams/provider-abstraction.mmd) — provider interface and factory selection

## Scope

This documentation describes only what is implemented in the repository as of Phase 5. Cloud provider adapters (Azure AI Foundry, Amazon Bedrock) and cloud deployment are referenced only as future, unimplemented extension points — see [`docs/cloud/`](../cloud/README.md) and [`docs/roadmap/README.md`](../roadmap/README.md) for their planned status.
