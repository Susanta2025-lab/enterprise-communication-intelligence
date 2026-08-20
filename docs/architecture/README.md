# ECI Platform Architecture Documentation

This directory documents the architecture implemented through **Phase 11A – Workflow Domain, State Machine & Authorization Foundation**. Provider adapters, cloud hosting, portable structured telemetry, application-user OIDC, GitHub OIDC CI/CD, user-owned PostgreSQL persistence, vendor-neutral communication connectors, and the approval-gated workflow domain are implemented. Workflow persistence, workflow HTTP, execution, managed cloud databases, production mailbox OAuth, and send/reply are not implemented.

## Contents

- [Overview](overview.md) — the implemented layered architecture end to end
- [Clean Architecture](clean-architecture.md) — how dependency direction and layering are applied
- [Dependency Flow](dependency-flow.md) — allowed and forbidden imports between layers
- [Application Layer](application-layer.md) — analysis, workflow, identity, history, ingestion, and connector-account services
- [Persistence](persistence.md) — PostgreSQL architecture, ownership, connector accounts, migrations, and proof level
- [Provider Abstraction](provider-abstraction.md) — `AIProvider`, mock, Foundry, Bedrock, the common LLM contract, and the factory
- [Project Structure](project-structure.md) — the actual repository layout and the role of each package
- [Sequence Diagrams](sequence-diagrams.md) — request-level walkthroughs, including connector ingestion

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
- [`identity.mmd`](../diagrams/identity.mmd) — application-user, AI workload, database, and deploy identity classes
- [`cicd.mmd`](../diagrams/cicd.mmd) — GitHub quality plus PostgreSQL CI; CD build-once to ACR/ACA and ECR/ECS
- [`ingress.mmd`](../diagrams/ingress.mmd) — Azure HTTPS live; AWS HTTP verification-only; ALB verified then torn down
- [`persistence.mmd`](../diagrams/persistence.mmd) — OIDC principal → identity mapping → analysis workflow → AI and PostgreSQL
- [`persistence-cloud.mmd`](../diagrams/persistence-cloud.mmd) — same application; future colocated Azure/AWS PostgreSQL not provisioned; CI `postgres:16` proof

## Scope

This documentation describes what is implemented in the repository as of Phase 11A. Cloud hosting uses one Docker image on Azure Container Apps and Amazon ECS Fargate. Application-user authentication is provider-independent OIDC JWT; live Entra is the first IdP. Persistence is PostgreSQL-compatible and proven in CI; managed Azure/AWS databases are not provisioned. Azure real-bearer requests are verified over managed HTTPS. AWS real-bearer TLS verification is not claimed. Observability uses the same stdout JSON on both clouds.

Phase 10 added a domain `CommunicationConnector` contract, `CommunicationIngestionService`, user-owned `connector_accounts`, and infrastructure adapters for fake, Gmail REST, and Microsoft Graph REST. Connector capability currently exists below the HTTP product surface. There is no connector HTTP API, production mailbox OAuth, credential resolver, background sync, or send/reply path. Controlled local live Gmail and Graph checks stopped at `CommunicationMessage`.

Phase 11A added `WorkflowAction`, an explicit reply-only state machine, and capability-specific permission checks. Analyzing a communication does not create a workflow action. `DraftReply` remains AI suggestion output. There is no workflow persistence, workflow REST API, execution port, or automatic reply path. See [`docs/cloud/`](../cloud/README.md), [`docs/cloud/authentication.md`](../cloud/authentication.md), [`docs/cloud/persistence.md`](../cloud/persistence.md), [`docs/cloud/observability.md`](../cloud/observability.md), [`docs/roadmap/phase-10-communication-connectors.md`](../roadmap/phase-10-communication-connectors.md), [`docs/roadmap/phase-11-workflow-automation.md`](../roadmap/phase-11-workflow-automation.md), and [`docs/roadmap/README.md`](../roadmap/README.md).
