# ECI Platform Architecture Documentation

This directory documents the architecture implemented through **Phase 18 – Secure Attachment Intelligence** (CLOSED / PASS), building on Phase 14 connected-mailbox read/analyze, Phase 15 browser SPA, Phase 16 cloud-hosted multi-cloud validation, and Phase 17 Microsoft Entra External ID product login (17A–17C CLOSED / PASS; 17D deferred).

Mailbox synchronization, search, bulk analysis, workers, and webhooks are not implemented. Multimodal JPEG/PNG attachment analysis is **not** live-supported (adapters report image input unavailable; images are gated before retrieval).

## Contents

- [Overview](overview.md) — the implemented layered architecture end to end
- [Clean Architecture](clean-architecture.md) — how dependency direction and layering are applied
- [Dependency Flow](dependency-flow.md) — allowed and forbidden imports between layers
- [Application Layer](application-layer.md) — analysis, workflow, identity, history, ingestion, connector-account, and workflow-execution services
- [Persistence](persistence.md) — PostgreSQL architecture, ownership, connector accounts, migrations, and proof level
- [Provider Abstraction](provider-abstraction.md) — `AIProvider`, mock, Foundry, Bedrock, the common LLM contract, and the factory
- [Project Structure](project-structure.md) — the actual repository layout and the role of each package
- [Sequence Diagrams](sequence-diagrams.md) — request-level walkthroughs, including connector ingestion, bounded mailbox listing, mailbox-backed analyze, workflow HTTP, user-approved execute, and a pointer to mailbox OAuth

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
- [`ingress.mmd`](../diagrams/ingress.mmd) — Azure HTTPS; AWS CloudFront HTTPS → HTTP ALB (Phase 16+)
- [`persistence.mmd`](../diagrams/persistence.mmd) — OIDC principal → identity mapping → analysis workflow → AI and PostgreSQL
- [`persistence-cloud.mmd`](../diagrams/persistence-cloud.mmd) — colocated Azure/AWS PostgreSQL topology (provisioned in Phase 16)

## Scope

Cloud hosting uses one Docker image on Azure Container Apps and Amazon ECS Fargate. Application-user authentication is provider-independent OIDC JWT; live product login is **Microsoft Entra External ID** (workforce Entra remains operator/admin/mailbox-OAuth directory context). Mailbox delegated OAuth is separate from application login. Persistence is PostgreSQL-compatible (CI-proven; managed Azure Flexible Server and Amazon RDS provisioned for cloud proofs; schema head includes `18d0001` for `attachment_analyses`).

Phase 18 adds metadata-only attachment listing, explicit single-attachment retrieve → ClamAV → parse → AI, and owner-scoped attachment-analysis history. ECI never retrieves or analyzes attachment content without an explicit user action for that attachment. Attachment analysis cannot Propose / Approve / Execute / Send. Crossed live validation: Outlook with Azure/Foundry and Gmail with AWS/Bedrock. See [Phase 18](../roadmap/phase-18-secure-attachment-intelligence.md).

Phase 10–14 connector and mailbox-read foundations remain. Analyze does not create a `WorkflowAction`. `DraftReply` remains AI suggestion output. There is no retry route and no automatic reply. See [`docs/cloud/`](../cloud/README.md), [`docs/cloud/authentication.md`](../cloud/authentication.md), [`docs/roadmap/README.md`](../roadmap/README.md).
