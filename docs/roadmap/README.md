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
| Phase 11 – Workflow Automation | In progress |

Phase 9A — Persistence Foundation is completed. Phase 9B — User Ownership & Analysis History is completed. Phase 9C — PostgreSQL Integration & CI is completed (GitHub run `32336909759`; 34 PostgreSQL tests; Alembic round-trip). Phase 9D — Cloud Strategy & Final Documentation is completed.

Phase 10A — Connector Architecture & Domain Contracts is completed. Phase 10B — Connector Accounts & Credential References is completed. Phase 10C — Gmail Read-Only Adapter is completed. Phase 10D — Microsoft Graph Read-Only Adapter is completed. Phase 10E — Documentation finalization is completed.

Phase 10 closed the vendor-neutral connector path through Gmail and Microsoft Graph read-only adapters, user-owned `connector_accounts`, and controlled local live adapter checks. Production OAuth, credential resolver, connector HTTP APIs, synchronization, and send/reply remain deferred. Details: [Phase 10](phase-10-communication-connectors.md).

Phase 11A — Workflow Domain, State Machine & Authorization Foundation is completed. Phase 11B — Workflow Persistence & User Ownership is completed. `WorkflowAction` is durable and user-owned; proposed replies are snapshotted at creation; analysis hard-delete leaves actions intact. Workflow REST API, execution, Gmail/Graph send/reply, production workflow automation, and automatic replies remain unavailable. Phase 11 overall is not completed. Details: [Phase 11](phase-11-workflow-automation.md).
