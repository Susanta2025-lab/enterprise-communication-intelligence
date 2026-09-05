# ECI Platform Project Roadmap

This directory documents the planned implementation phases for ECI Platform.

## Phases

- [Phase 1 – Foundation](phase-01-foundation.md)
- [Phase 2 – Domain Model](phase-02-domain-model.md)
- [Phase 3 – Provider Abstraction](phase-03-provider-abstraction.md)
- [Phase 4 – AI Services](phase-04-ai-services.md)
- [Phase 5 – REST API](phase-05-rest-api.md)
- [Phase 6 – Cloud Deployment](phase-06-cloud-deployment.md)
- [Phase 7 – Observability](phase-07-observability.md)
- [Phase 8 – Production Hardening](phase-08-future-roadmap.md)
- [Phase 9 – Persistence & Multi-Tenant/User-Associated Data](phase-09-persistence.md)
- [Phase 10 – Communication Connectors](phase-10-communication-connectors.md)
- [Phase 11 – Workflow Automation](phase-11-workflow-automation.md)
- [Phase 12 – Production Communication Execution](phase-12-production-communication-execution.md)
- [Phase 13 – Production Mailbox OAuth](phase-13-mailbox-delegated-oauth.md)
- [Phase 14 – Connected Mailbox Read and Analysis](phase-14-connected-mailbox-analysis.md)
- [Phase 15 – Browser Frontend](phase-15-frontend.md)
- [Phase 16 – Cloud-Hosted Browser & End-to-End Multi-Cloud Validation](phase-16-cloud-browser-multicloud-validation.md)
- [Phase 17 – Microsoft Entra External ID & External User Onboarding](phase-17-external-id-external-user-onboarding.md)

## Status

| Phase | Status |
|---|---|
| Phase 1 – Foundation | Completed |
| Phase 2 – Domain Model | Completed |
| Phase 3 – Provider Abstraction | Completed |
| Phase 4 – AI Services | Completed |
| Phase 5 – REST API | Completed |
| Phase 6 – Cloud Deployment | Completed |
| Phase 7 – Observability | Completed |
| Phase 8 – Production Hardening | Completed |
| Phase 9 – Persistence & Multi-Tenant/User-Associated Data | Completed |
| Phase 10 – Communication Connectors | Completed |
| Phase 11 – Workflow Automation | Completed |
| Phase 12 – Production Communication Execution | Completed |
| Phase 13 – Production Mailbox OAuth | Completed |
| Phase 14 – Connected Mailbox Read and Analysis | Completed |
| Phase 15 – Browser Frontend | Completed |
| Phase 16 – Cloud-Hosted Browser & End-to-End Multi-Cloud Validation | Completed |
| Phase 17 – Microsoft Entra External ID & External User Onboarding | Next |

Phase 9A — Persistence Foundation is completed. Phase 9B — User Ownership & Analysis History is completed. Phase 9C — PostgreSQL Integration & CI is completed (GitHub run `32336909759`; 34 PostgreSQL tests; Alembic round-trip). Phase 9D — Cloud Strategy & Final Documentation is completed.

Phase 10A — Connector Architecture & Domain Contracts is completed. Phase 10B — Connector Accounts & Credential References is completed. Phase 10C — Gmail Read-Only Adapter is completed. Phase 10D — Microsoft Graph Read-Only Adapter is completed. Phase 10E — Documentation finalization is completed.

Phase 10 closed the vendor-neutral connector path through Gmail and Microsoft Graph read-only adapters, user-owned `connector_accounts`, and controlled local live adapter checks. Production OAuth, credential resolver, connector HTTP APIs, synchronization, and send/reply remain deferred. Details: [Phase 10](phase-10-communication-connectors.md).

Phase 11A — Workflow Domain, State Machine & Authorization Foundation is completed. Phase 11B — Workflow Persistence & User Ownership is completed. Phase 11C — Workflow Proposal and Approval API is completed. Phase 11D — Action Execution Port + Deterministic Fake Executor is completed. Phase 11E — Integration, Documentation & Regression is completed. `WorkflowAction` is durable, user-owned, and exposed over `/api/v1/workflow-actions` for create, list, get, approve, and reject. Execution exists below HTTP through `CommunicationActionExecutor` and a deterministic fake. HTTP execute, Gmail/Graph send/reply, production workflow automation, and automatic replies remain unavailable. Phase 11 overall is completed. Details: [Phase 11](phase-11-workflow-automation.md).

Phase 12A — Execution Target, Routing & Executability Foundation is completed. Phase 12B — Credential Resolution + Write-Scope Readiness is completed. Phase 12C — Microsoft Graph Reply Executor is completed. Phase 12D — Gmail Reply Executor is completed. Phase 12E — Execute API + `communications:send` is completed: owned-account factory routing, Gmail profile mailbox identity, and `POST /api/v1/workflow-actions/{action_id}/execute`. Phase 12F is completed: failure semantics, privacy, documentation, ADR-020, and regression. Phase 12 overall is completed. It delivered user-approved real communication execution. It did not deliver automatic replies, production OAuth refresh, managed secret stores, retry/reconciliation, `EXECUTION_UNKNOWN`, exactly-once execution, or live-provider certification. Automatic replies remain deferred. Details: [Phase 12](phase-12-production-communication-execution.md).

Phase 13A — OAuth Domain, Authorization Session & Security Foundation is completed. Phase 13B — Credential Store + Refreshable Access-Token Foundation is completed. Phase 13C — Google OAuth / Gmail Credential Lifecycle is completed (live Google consent and an explicitly approved Gmail reply validated locally). Phase 13D — Microsoft Entra OAuth / Graph Credential Lifecycle is completed (live Entra consent and an explicitly approved Graph reply validated locally). Phase 13E — Azure Key Vault + AWS Secrets Manager production backends is completed (PostgreSQL advisory-lock coordination; live Azure Key Vault and AWS Secrets Manager store validation). AWS Secrets Manager `get()`/`delete()` treat secrets scheduled for deletion as absent after `DescribeSecret` confirms `DeletedDate`; required IAM includes `secretsmanager:DescribeSecret` on `eci/mailbox-oauth/*` and does not include `ListSecrets`. Phase 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression is completed. After 13F, a controlled local live Gmail disconnect → exact-account reauthorization was validated (same connector row `eaae1e04-89a9-4c90-a2c1-f9036438de25`; capabilities restored to `mail.read` and `mail.send`). That is not cloud-hosted ACA/ECS OAuth certification. Phase 13 overall is completed. Details: [Phase 13](phase-13-mailbox-delegated-oauth.md).

Phase 14A — Read Authorization + Public Contract is completed. Phase 14B — Provider-Neutral Read Connector Factory is completed. Phase 14C — Connected Message → AI Analysis is completed. Phase 14D — Bounded Mailbox Message Listing is completed. Phase 14E — Lifecycle / Privacy / Failure Hardening is completed. Phase 14F — Final Documentation, Observability, Live Validation & Regression is completed: privacy-safe Gmail ID-token verification diagnostics retained as production observability (`verify_error_class` and verified-claim presence flags only; validation not weakened); live Entra `communications:read` provisioned with the previous four ECI scopes preserved; local-runtime Gmail and Microsoft Graph bounded list → selected-message analyze with `MockAIProvider`; connectors remained `ACTIVE` after normal successful access; no automatic workflow/send; README audit and full offline regression. That is not ACA-hosted or ECS-hosted Phase 14 mailbox→AI certification and did not call Foundry or Bedrock. Phase 14 overall is completed. Details: [Phase 14](phase-14-connected-mailbox-analysis.md).

Phase 15A — Frontend Foundation + Browser Authentication is completed: same-repository React + TypeScript + Vite SPA, MSAL public-client login, lazy ECI bearer tokens, `GET /api/v1/analyses?limit=1` smoke contract, explicit CORS allowlist, ADR-025. Phase 15B — Connector Dashboard + OAuth UX is completed: owned connector-account dashboard, server-side Gmail/Graph connect and reauthorize UX, disconnect confirmation, optional `FRONTEND_OAUTH_RETURN_URL` callback return. Phase 15C — Mailbox Workspace + Pagination is completed: ACTIVE-connector mailbox workspace, bounded list, opaque cursor Load more, in-memory selection. Phase 15D — Analysis Experience is completed: explicit selected-message analyze in the mailbox workspace, in-memory analysis display, read-only AI draft suggestion. Phase 15E — Workflow Review + Explicit Send UX is completed: explicit WorkflowAction proposal, immutable snapshot review, explicit approve/reject, confirmed send, and EXECUTING uncertainty without retry. Live send was not performed. Phase 15F — Error / Accessibility / Responsive Hardening is completed: context-safe error mapping, ErrorBoundary, dialog focus, keyboard/responsive hardening, and axe-backed tests. Phase 15G — Live Browser Validation + Documentation + Phase Closure is completed: real MSAL browser authentication, all five ECI delegated permissions, Gmail and Microsoft Graph bounded live list/analyze/propose/approve with `MockAIProvider`, exact-account reauthorization recovery for both providers, stop before Send/execute, frontend CI job, documentation reconciliation, and full offline regression. That is local Vite + local FastAPI + local PostgreSQL; it is not ACA/ECS-hosted browser certification and did not call Foundry or Bedrock on the mailbox analyze path. Details: [Phase 15](phase-15-frontend.md).

Phase 16A — Cloud Runtime / Deployment Readiness is completed: authenticated read-only Azure and AWS inventory, ADR-026 topology freeze (Azure Static Web Apps → ACA; AWS S3/CloudFront SPA and CloudFront → HTTP ALB → ECS without a custom domain), colocated sequential PostgreSQL, mandatory Key Vault / Secrets Manager, configuration and cost/authorization gates. No cloud resources were created or mutated in 16A. Phase 16B — Azure Full-Stack Browser Deployment is completed: Azure Static Web Apps `eci-web-dev`, Azure Database for PostgreSQL Flexible Server `eci-pg-dev-susanta`, then-current ACA image `eci-api:7518360`, Key Vault Secrets Officer on the runtime UAMI, Entra/MSAL browser smoke against ACA. Phase 16C — Azure Live Mailbox → Microsoft Foundry Validation is completed: Graph delegated OAuth, Key Vault credential durability across an ACA same-revision recycle, one `MicrosoftFoundryProvider` selected-message analysis, explicit Propose (PENDING) then explicit Approve (APPROVED), stop before Send. No Gmail, Bedrock, AWS, execute, or live Send in that slice. Phase 16D — AWS HTTPS + Full-Stack Browser Deployment is **COMPLETE / PASS**: private S3 + CloudFront OAC SPA `https://d1ut7j94w7lt3b.cloudfront.net`, API CloudFront `https://dnookm0ucbhv1.cloudfront.net` → HTTP ALB → ECS (historical task definition `eci-api-dev:6`, image `0050b30`), RDS `eci-pg-dev`, Secrets Manager credential-store backend, Entra/MSAL, CORS, protected analyses and connector-list reads. Connector-list 503 resolved by decoupling listing from the OAuth store. That slice did not call Gmail, Graph mailbox, Bedrock inference, or Send. Phase 16E — AWS Gmail → Bedrock validation is **Completed**: Gmail mailbox → Amazon Bedrock Analyze → Propose → Approve; historical 16E included one manual Send. Phase 16F-A1 — Connector UX Redesign is **Completed**. Phase 16F-A2 — Safe Mailbox Identity and Connect-Another Backend Contract is **Completed**: optional presentation-only `display_identity`; `CONNECT_ANOTHER` with provider account selection; reconnect remains exact-account. Remaining 16F is **Completed**: Azure Outlook connect-another / reactivation + Foundry regression and AWS Gmail multi-account + Bedrock regression, both stopping before Send; compute scaled to zero; both managed databases stopped. Current retained lineage is application `3fa3412`, schema `16f0001`, AWS task definition `eci-api-dev:8`. Details: [Phase 16](phase-16-cloud-browser-multicloud-validation.md).

Phase 17A — External ID Readiness Assessment is **Completed / PASS**. Phase 17B-A — ADR / Architecture Lock is **Completed / PASS**: [ADR-027](../decisions/ADR-027-microsoft-entra-external-id-customer-authentication.md) locks Microsoft Entra External ID as the exclusive ECI product-login IdP, email OTP as the initial customer path, retained `(iss, sub)` mapping, no dual issuer, no schema migration, and mailbox-login separation. Phase 17B-B — Frontend External ID / MSAL Configuration is **Completed / PASS**: explicit CIAM `VITE_ENTRA_AUTHORITY` and derived `knownAuthorities`; existing MSAL SPA retained. Next is 17B-C backend External ID JWT / configuration. 17C controlled owner-account validation and 17D Sally verification remain later. Details: [Phase 17](phase-17-external-id-external-user-onboarding.md).
