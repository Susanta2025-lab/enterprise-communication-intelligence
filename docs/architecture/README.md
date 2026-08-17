# ECI Platform Architecture Documentation

This directory documents the architecture implemented through **Phase 6C – Deployment Foundation**. Provider adapters and cloud hosting (Azure Container Apps and ECS Fargate) are implemented.

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

## Scope

This documentation describes what is implemented in the repository as of Phase 6C. Cloud hosting uses one Docker image on Azure Container Apps and Amazon ECS Fargate — see [`docs/cloud/`](../cloud/README.md) and [`docs/roadmap/README.md`](../roadmap/README.md).
