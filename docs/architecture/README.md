# ECI Platform Architecture Documentation

This directory documents the architecture implemented through **Phase 13 – Production Mailbox OAuth**. Phase 12 (user-approved execute, ADR-020 failure semantics) remains completed. Phase 13 adds delegated Gmail and Microsoft Graph OAuth, opaque credential stores (including Azure Key Vault and AWS Secrets Manager), PostgreSQL advisory-lock coordination, disconnect/reauthorization HTTP, and automatic `REAUTH_REQUIRED` on confirmed permanent refresh failure. Managed cloud databases are not provisioned. User-facing connector message-ingestion HTTP is not implemented.

## Contents

- [Overview](overview.md) — the implemented layered architecture end to end
- [Clean Architecture](clean-architecture.md) — how dependency direction and layering are applied
- [Dependency Flow](dependency-flow.md) — allowed and forbidden imports between layers
- [Application Layer](application-layer.md) — analysis, workflow, identity, history, ingestion, connector-account, and workflow-execution services
- [Persistence](persistence.md) — PostgreSQL architecture, ownership, connector accounts, migrations, and proof level
- [Provider Abstraction](provider-abstraction.md) — `AIProvider`, mock, Foundry, Bedrock, the common LLM contract, and the factory
- [Project Structure](project-structure.md) — the actual repository layout and the role of each package
- [Sequence Diagrams](sequence-diagrams.md) — request-level walkthroughs, including connector ingestion, workflow HTTP, user-approved execute, and a pointer to mailbox OAuth

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
- [`identity.mmd`](../diagrams/identity.mmd) — application-user, mailbox delegated, AI workload, database, and deploy identity classes
- [`mailbox-oauth.mmd`](../diagrams/mailbox-oauth.mmd) — Phase 13 mailbox OAuth and credential-store lifecycle
- [`cicd.mmd`](../diagrams/cicd.mmd) — GitHub quality plus PostgreSQL CI; CD build-once to ACR/ACA and ECR/ECS
- [`ingress.mmd`](../diagrams/ingress.mmd) — Azure HTTPS live; AWS HTTP verification-only; ALB verified then torn down
- [`persistence.mmd`](../diagrams/persistence.mmd) — OIDC principal → identity mapping → analysis workflow → AI and PostgreSQL
- [`persistence-cloud.mmd`](../diagrams/persistence-cloud.mmd) — same application; future colocated Azure/AWS PostgreSQL not provisioned; CI `postgres:16` proof

## Scope

This documentation describes what is implemented in the repository as of Phase 13 (completed; 13A–13F completed). Cloud hosting uses one Docker image on Azure Container Apps and Amazon ECS Fargate. Application-user authentication is provider-independent OIDC JWT; live Entra is the first IdP. Mailbox delegated OAuth is separate from that login. Persistence is PostgreSQL-compatible and proven in CI; managed Azure/AWS databases are not provisioned. Azure real-bearer requests are verified over managed HTTPS. AWS real-bearer TLS verification is not claimed. Observability uses the same stdout JSON on both clouds.

Phase 10 added a domain `CommunicationConnector` contract, `CommunicationIngestionService`, user-owned `connector_accounts`, and infrastructure adapters for fake, Gmail REST, and Microsoft Graph REST. Connector fetch capability currently exists below the HTTP product surface. There is no connector message-ingestion HTTP, background sync, or automatic reply. Phase 13 adds mailbox OAuth lifecycle HTTP (authorize, callback, disconnect, reauthorize). Phase 12B adds `CommunicationCredentialResolver` as an environment-backed local/dev boundary for legacy locators. Production mailbox credentials use the opaque store. Controlled local live Gmail and Graph OAuth, including explicitly approved replies, are recorded on the Phase 13 roadmap; that is not cloud-hosted certification of the retained ACA/ECS services.

Phase 11A added `WorkflowAction`, an explicit reply-only state machine, and capability-specific permission checks. Phase 11B persists user-owned `workflow_actions` with a proposed-reply snapshot and no analysis FK. Phase 11C exposes create, list, get, approve, and reject over `/api/v1/workflow-actions`. Phase 11D adds `CommunicationActionExecutor`, a deterministic fake executor, and `WorkflowActionExecutionService`. Phase 12A snapshots mailbox execution-target provenance onto analyses and workflow actions and validates an owned active `ConnectorAccount` inside the execution unit of work before the `APPROVED` → `EXECUTING` write, TX1 commit, or executor call. Phase 12B adds `CommunicationCredentialResolver`. Phase 12C and 12D add Graph and Gmail reply adapters. Phase 12E routes those adapters through `CommunicationActionExecutorFactory` and `POST /api/v1/workflow-actions/{action_id}/execute` protected by `communications:send`. Phase 12F records uncertain-outcome semantics in ADR-020: definite rejection becomes `FAILED`, confirmed success becomes `EXECUTED`, and uncertain/unavailable post-TX1 outcomes remain `EXECUTING` with HTTP 503. Analyzing a communication does not create a workflow action. `DraftReply` remains AI suggestion output. There is no retry route and no automatic reply. See [`docs/cloud/`](../cloud/README.md), [`docs/cloud/authentication.md`](../cloud/authentication.md), [`docs/cloud/persistence.md`](../cloud/persistence.md), [`docs/cloud/observability.md`](../cloud/observability.md), [`docs/roadmap/phase-10-communication-connectors.md`](../roadmap/phase-10-communication-connectors.md), [`docs/roadmap/phase-11-workflow-automation.md`](../roadmap/phase-11-workflow-automation.md), [`docs/roadmap/phase-12-production-communication-execution.md`](../roadmap/phase-12-production-communication-execution.md), and [`docs/roadmap/README.md`](../roadmap/README.md).
