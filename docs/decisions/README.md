# Architecture Decision Records (ADRs)

## Purpose

ADRs capture significant architectural decisions for ECI Platform, along with the context and alternatives that were considered, so future contributors understand *why* the system is structured the way it is — not just what it currently looks like.

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
| [ADR-006](ADR-006-azure-ai-foundry.md) | Microsoft Foundry Provider | Accepted |
| [ADR-007](ADR-007-amazon-bedrock.md) | Amazon Bedrock Provider | Accepted |
| [ADR-008](ADR-008-observability.md) | Portable Structured Observability | Accepted |
| [ADR-009](ADR-009-application-user-authentication.md) | Application-User Authentication and Authorization | Accepted |
| [ADR-010](ADR-010-multi-cloud-ingress.md) | Multi-Cloud Production Ingress Strategy | Accepted |
| [ADR-011](ADR-011-github-actions-oidc-cicd.md) | Secretless GitHub Actions Multi-Cloud CI/CD | Accepted |
| [ADR-012](ADR-012-postgresql-persistence-architecture.md) | PostgreSQL Persistence Architecture | Accepted |
| [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md) | External Identity Mapping and User-Owned Data | Accepted |
| [ADR-014](ADR-014-cloud-postgresql-deployment-strategy.md) | Cloud PostgreSQL Deployment Strategy | Accepted |
| [ADR-015](ADR-015-approval-gated-workflow-actions.md) | Approval-Gated Workflow Actions | Accepted |
| [ADR-016](ADR-016-workflow-persistence-and-analysis-provenance.md) | Workflow Persistence and Analysis Provenance | Accepted |
| [ADR-017](ADR-017-communication-action-execution-boundary.md) | Communication Action Execution Boundary | Accepted |
| [ADR-018](ADR-018-workflow-execution-target-provenance.md) | Workflow Execution Target Provenance | Accepted |
| [ADR-019](ADR-019-production-communication-write-architecture.md) | Production Communication Write Architecture | Accepted |
| [ADR-020](ADR-020-uncertain-communication-execution-semantics.md) | Uncertain Communication Execution Semantics | Accepted |
| [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md) | Mailbox Delegated OAuth Authorization Architecture | Accepted |
| [ADR-022](ADR-022-opaque-communication-credential-store-and-refreshable-access-tokens.md) | Opaque Communication Credential Store and Refreshable Access Tokens | Accepted |
| [ADR-023](ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md) | Mailbox Credential Lifecycle, Disconnect and Reauthorization | Accepted |
| [ADR-024](ADR-024-connected-mailbox-read-and-analysis-authorization-boundary.md) | Connected Mailbox Read and Analysis Authorization Boundary | Accepted |
| [ADR-025](ADR-025-browser-frontend-and-authentication-architecture.md) | Browser Frontend and Authentication Architecture | Accepted |

ADR-007 records the Amazon Bedrock adapter decision. The decision is implemented, covered by offline tests, and live-verified through ECI.

ADR-008 records the Phase 7 observability decision: portable structured logs with request correlation, plus native Azure and AWS log retention and platform metrics. Tracing and custom metric infrastructure remain deferred.

ADR-009 records provider-independent OIDC JWT validation and permission `communications:analyze`. Live Entra is the first IdP. Azure real-bearer requests are verified; AWS real bearer is deferred until TLS.

ADR-010 records Azure Container Apps managed HTTPS as live ingress, and AWS ALB as verified then torn down. Direct AWS task HTTP is verification-only.

ADR-011 records automatic tests-only CI and manual multi-cloud CD with GitHub OIDC. First verified deploy is commit `dd55327` with identical ACR and ECR digests.

ADR-012 records PostgreSQL as the production system of record, with SQLAlchemy 2.x, Alembic, and SQLite only for local/test use.

ADR-013 records OIDC `(issuer, subject)` mapping onto an opaque internal user UUID and user-associated ownership isolation. That is not SaaS tenancy.

ADR-014 records Option C: cloud-portable PostgreSQL plus ephemeral CI proof. Shared cross-cloud databases and dual standing managed databases are rejected for this phase. No Azure PostgreSQL or Amazon RDS is provisioned.

ADR-015 records that AI suggestions are not authorized external actions. `WorkflowAction` requires an explicit proposal and human approval. `CommunicationConnector` stays read-only. Authorization checks capability-specific permissions (`communications:analyze` vs `communications:workflow`). Persistence and HTTP were later Phase 11 slices; the execution boundary is recorded in [ADR-017](ADR-017-communication-action-execution-boundary.md).

ADR-016 records that workflow actions persist as user-owned `workflow_actions` rows. The proposed reply is snapshotted at creation. Approval writes a separate authorized snapshot. `analysis_id` is required provenance without a database FK, so analysis hard-delete leaves actions intact. HTTP was added in Phase 11C. Execution is recorded in [ADR-017](ADR-017-communication-action-execution-boundary.md) without changing this persistence decision.

ADR-017 records the Phase 11D execution boundary: `CommunicationActionExecutor` is a write port separate from `CommunicationConnector`. `WorkflowActionExecutionService` commits `APPROVED` → `EXECUTING` before the fake executor runs, holds no database transaction during the call, then records `EXECUTED` or `FAILED`. There is no HTTP execute route and no real provider write.

ADR-018 records Phase 12A execution-target provenance. `WorkflowAction` snapshots `connector_account_id` and `provider_message_id` at create. Analyses store optional mailbox `connector_account_id`. Execution validates an owned active connector account inside the execution unit of work before the `APPROVED` → `EXECUTING` write, TX1 commit, or executor call. Legacy targetless rows remain valid and non-executable. Credentials are not stored on workflow or analysis rows.

ADR-019 records production write architecture. `CommunicationConnector` stays read-only. `MicrosoftGraphCommunicationActionExecutor` and `GmailCommunicationActionExecutor` implement `CommunicationActionExecutor` with injected `httpx.Client` and `AccessTokenProvider`. Graph uses native `/reply`. Gmail discovers sender identity from `users/me/profile`, fetches metadata, constructs an RFC 2822 reply, and posts `messages.send`. Tokens and `credential_ref` stay off the execution command. Phase 12E routes those writers through `CommunicationActionExecutorFactory` and `POST /api/v1/workflow-actions/{action_id}/execute` protected by `communications:send`.

ADR-020 records uncertain external-side-effect semantics. Definite provider rejection becomes durable `FAILED`. Confirmed success becomes durable `EXECUTED`. Uncertain or unavailable outcomes after TX1 remain `EXECUTING` and the execute API returns HTTP 503. Automatic retry and `EXECUTION_UNKNOWN` are rejected. Duplicate-send prevention takes priority over automatic recovery. Operator reconciliation remains future work.

ADR-021 records mailbox delegated OAuth as a server-side authorization transaction separate from ECI application-user OIDC. Raw OAuth state is not persisted; SHA-256(state) is. State is single-use via a conditional consume compare-and-set and bound to the internal user plus mailbox provider. PKCE is S256. `communications:connect` is distinct from analyze/workflow/send. `credential_ref` remains non-unique at the database level. 13A disconnect cleared locator and grant metadata without provider token revocation. Real Google/Microsoft OAuth, secret-store backends, operational disconnect HTTP, exact-account reauthorization, and permanent-refresh `REAUTH_REQUIRED` were delivered in 13C–13F. See [ADR-023](ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md).

ADR-022 records the provider-neutral credential store and refreshable access-token foundation. `ConnectorAccount` stores only an opaque `credential_ref`. Secrets live outside PostgreSQL. `resolve()` performs no secret or token I/O. Compare-and-set replacement is the store contract. Phase 13C/13D added real Google and Microsoft refresh adapters. Phase 13E durable Azure/AWS backends serialize cloud mutations with PostgreSQL advisory locks keyed by that locator because Azure Key Vault does not provide linearizable CAS. AWS retains native version/stage compare-and-set in addition. PostgreSQL stores no OAuth secrets. The environment resolver remains the local/dev execute default for legacy locators. Production mailbox OAuth uses Key Vault or Secrets Manager.

ADR-023 records mailbox credential lifecycle. Local disconnect is the authoritative removal of ECI delegated access. Google token revocation is best-effort after local success. Microsoft `revokeSignInSessions` is not used. Reauthorization is bound to the exact owned account and rejected unless the verified mailbox identity matches. Confirmed permanent refresh failure marks that account `REAUTH_REQUIRED` and records a definite no-send `FAILED` workflow outcome. Transient credential unavailability keeps Phase 12 `503`/`EXECUTING`. After 13F, a controlled local live Gmail disconnect → exact-account reauthorization was validated (same connector row; not cloud-hosted ACA/ECS certification).

ADR-024 records that `communications:read` is distinct from connect, analyze, workflow, and send. Mailbox listing requires `communications:read`. Mailbox-backed AI analysis requires `communications:read` and `communications:analyze`. Direct-text analyze remains `communications:analyze` only. ECI `communications:read` is not provider `mail.read`. Connector ownership, lifecycle, and grant metadata remain resource-level gates. Public provider message ids and pagination cursors stay opaque. `CommunicationConnector` remains the read boundary and stays separate from `CommunicationActionExecutor`. Live Entra now provisions `communications:read` with the previous four ECI scopes. Phase 14 locally live-validated Gmail and Graph list → selected-message analyze with real OIDC tokens and `MockAIProvider`; that is not ACA/ECS or Foundry/Bedrock certification.

ADR-025 records the Phase 15A browser foundation: same-repository React + TypeScript + Vite SPA, MSAL public client, FastAPI bearer tokens, no BFF or application cookies, mailbox OAuth remaining server-side, TanStack Query for server state, and an explicit CORS origin allowlist. A dedicated Entra SPA registration is preferred for live browser operation and was not created in 15A.

## Template

Use [`ADR-template.md`](ADR-template.md) as the starting point for any new ADR.
