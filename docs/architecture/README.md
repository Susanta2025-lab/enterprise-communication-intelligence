# ECI Platform Architecture Documentation

This directory documents the architecture implemented through **Phase 7 – Observability**. Provider adapters, cloud hosting, and portable structured telemetry are implemented.

## Contents

- [Overview](overview.md) — the implemented layered architecture end to end
- [Clean Architecture](clean-architecture.md) — how dependency direction and layering are applied
- [Dependency Flow](dependency-flow.md) — allowed and forbidden imports between layers
- [Application Layer](application-layer.md) — `CommunicationAnalysisService` responsibilities
- [Provider Abstraction](provider-abstraction.md) — `AIProvider`, mock, Foundry, Bedrock, the common LLM contract, and the factory
- [Project Structure](project-structure.md) — the actual repository layout and the role of each package
- [Sequence Diagrams](sequence-diagrams.md) — request-level walkthroughs

## Diagrams

Mermaid source files live in [`docs/diagrams/`](../diagrams/README.md):

- [`architecture.mmd`](../diagrams/architecture.mmd) — layered system diagram
- [`request-flow.mmd`](../diagrams/request-flow.mmd) — successful and failure request sequences
- [`provider-abstraction.mmd`](../diagrams/provider-abstraction.mmd) — provider interface and factory selection
- [`deployment-azure.mmd`](../diagrams/deployment-azure.mmd) — Azure Container Apps hosting path
- [`deployment-aws.mmd`](../diagrams/deployment-aws.mmd) — ECS Fargate hosting path
- [`observability-application.mmd`](../diagrams/observability-application.mmd) — request_id and structured stdout telemetry
- [`observability-azure.mmd`](../diagrams/observability-azure.mmd) — Log Analytics and native Container Apps metrics
- [`observability-aws.mmd`](../diagrams/observability-aws.mmd) — CloudWatch Logs and standard ECS metrics

## Scope

This documentation describes what is implemented in the repository as of Phase 7. Cloud hosting uses one Docker image on Azure Container Apps and Amazon ECS Fargate. Observability uses the same stdout JSON on both clouds — see [`docs/cloud/`](../cloud/README.md), [`docs/cloud/observability.md`](../cloud/observability.md), and [`docs/roadmap/README.md`](../roadmap/README.md).
