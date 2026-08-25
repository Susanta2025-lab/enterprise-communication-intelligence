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
| Phase 15 – Browser Frontend | In progress (15A completed; 15B next) |

Phase 9A — Persistence Foundation is completed. Phase 9B — User Ownership & Analysis History is completed. Phase 9C — PostgreSQL Integration & CI is completed (GitHub run `32336909759`; 34 PostgreSQL tests; Alembic round-trip). Phase 9D — Cloud Strategy & Final Documentation is completed.

Phase 10A — Connector Architecture & Domain Contracts is completed. Phase 10B — Connector Accounts & Credential References is completed. Phase 10C — Gmail Read-Only Adapter is completed. Phase 10D — Microsoft Graph Read-Only Adapter is completed. Phase 10E — Documentation finalization is completed.

Phase 10 closed the vendor-neutral connector path through Gmail and Microsoft Graph read-only adapters, user-owned `connector_accounts`, and controlled local live adapter checks. Production OAuth, credential resolver, connector HTTP APIs, synchronization, and send/reply remain deferred. Details: [Phase 10](phase-10-communication-connectors.md).

Phase 11A — Workflow Domain, State Machine & Authorization Foundation is completed. Phase 11B — Workflow Persistence & User Ownership is completed. Phase 11C — Workflow Proposal and Approval API is completed. Phase 11D — Action Execution Port + Deterministic Fake Executor is completed. Phase 11E — Integration, Documentation & Regression is completed. `WorkflowAction` is durable, user-owned, and exposed over `/api/v1/workflow-actions` for create, list, get, approve, and reject. Execution exists below HTTP through `CommunicationActionExecutor` and a deterministic fake. HTTP execute, Gmail/Graph send/reply, production workflow automation, and automatic replies remain unavailable. Phase 11 overall is completed. Details: [Phase 11](phase-11-workflow-automation.md).

Phase 12A — Execution Target, Routing & Executability Foundation is completed. Phase 12B — Credential Resolution + Write-Scope Readiness is completed. Phase 12C — Microsoft Graph Reply Executor is completed. Phase 12D — Gmail Reply Executor is completed. Phase 12E — Execute API + `communications:send` is completed: owned-account factory routing, Gmail profile mailbox identity, and `POST /api/v1/workflow-actions/{action_id}/execute`. Phase 12F is completed: failure semantics, privacy, documentation, ADR-020, and regression. Phase 12 overall is completed. It delivered user-approved real communication execution. It did not deliver automatic replies, production OAuth refresh, managed secret stores, retry/reconciliation, `EXECUTION_UNKNOWN`, exactly-once execution, or live-provider certification. Automatic replies remain deferred. Details: [Phase 12](phase-12-production-communication-execution.md).

Phase 13A — OAuth Domain, Authorization Session & Security Foundation is completed. Phase 13B — Credential Store + Refreshable Access-Token Foundation is completed. Phase 13C — Google OAuth / Gmail Credential Lifecycle is completed (live Google consent and an explicitly approved Gmail reply validated locally). Phase 13D — Microsoft Entra OAuth / Graph Credential Lifecycle is completed (live Entra consent and an explicitly approved Graph reply validated locally). Phase 13E — Azure Key Vault + AWS Secrets Manager production backends is completed (PostgreSQL advisory-lock coordination; live Azure Key Vault and AWS Secrets Manager store validation). AWS Secrets Manager `get()`/`delete()` treat secrets scheduled for deletion as absent after `DescribeSecret` confirms `DeletedDate`; required IAM includes `secretsmanager:DescribeSecret` on `eci/mailbox-oauth/*` and does not include `ListSecrets`. Phase 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression is completed. After 13F, a controlled local live Gmail disconnect → exact-account reauthorization was validated (same connector row `eaae1e04-89a9-4c90-a2c1-f9036438de25`; capabilities restored to `mail.read` and `mail.send`). That is not cloud-hosted ACA/ECS OAuth certification. Phase 13 overall is completed. Details: [Phase 13](phase-13-mailbox-delegated-oauth.md).

Phase 14A — Read Authorization + Public Contract is completed. Phase 14B — Provider-Neutral Read Connector Factory is completed. Phase 14C — Connected Message → AI Analysis is completed. Phase 14D — Bounded Mailbox Message Listing is completed. Phase 14E — Lifecycle / Privacy / Failure Hardening is completed. Phase 14F — Final Documentation, Observability, Live Validation & Regression is completed: privacy-safe Gmail ID-token verification diagnostics retained as production observability (`verify_error_class` and verified-claim presence flags only; validation not weakened); live Entra `communications:read` provisioned with the previous four ECI scopes preserved; local-runtime Gmail and Microsoft Graph bounded list → selected-message analyze with `MockAIProvider`; connectors remained `ACTIVE` after normal successful access; no automatic workflow/send; README audit and full offline regression. That is not ACA-hosted or ECS-hosted Phase 14 mailbox→AI certification and did not call Foundry or Bedrock. Phase 14 overall is completed. Details: [Phase 14](phase-14-connected-mailbox-analysis.md).

Phase 15A — Frontend Foundation + Browser Authentication is completed: same-repository React + TypeScript + Vite SPA, MSAL public-client login, lazy ECI bearer tokens, `GET /api/v1/analyses?limit=1` smoke contract, explicit CORS allowlist, ADR-025. Live Entra SPA registration and real browser authentication remain deferred operator steps. Phase 15B — Connector Dashboard + OAuth UX is next. Details: [Phase 15](phase-15-frontend.md).
