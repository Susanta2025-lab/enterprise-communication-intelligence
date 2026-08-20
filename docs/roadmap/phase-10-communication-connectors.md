# Phase 10 — Communication Connectors

## Objective

Introduce a vendor-neutral communication connector boundary so external adapters can supply already-normalized `CommunicationMessage` values to the existing analysis workflow, without Gmail/Graph SDKs, OAuth, connector persistence, or API routes.

## Business Value

- Proves the path: external adapter → `CommunicationConnector` → `CommunicationIngestionService` → `CommunicationAnalysisWorkflowService`.
- Keeps email as a `SourceType` medium. Vendor identity stays out of the domain enum.
- Keeps AI analysis, persistence, and HTTP outside connector adapters.

## Status

Phase 10 is **In progress**.

- **10A is implementation complete / review pending:** domain connector contract, connector-neutral errors, ingestion service, offline fake adapter, unit and boundary tests. No API, OAuth, migrations, or vendor SDKs.
- **10B is pending.**
- **10C is pending.**
- **10D is pending.**
- **10E is pending.**

Do not implement Gmail, Microsoft Graph, OAuth, connector accounts, or connector API routes in 10A.

## Deliverables

- [x] Phase 10A — Connector Architecture & Domain Contracts (implementation complete; review pending)
- [ ] Phase 10B — pending
- [ ] Phase 10C — pending
- [ ] Phase 10D — pending
- [ ] Phase 10E — pending

## Phase 10A Architecture

```text
CommunicationConnector (domain)
        ↑
FakeCommunicationConnector (infrastructure.connectors.fake)
        ↓
CommunicationIngestionService (application)
        ↓
CommunicationAnalysisWorkflowService (existing)
        ↓
CommunicationAnalysisService → AIProvider
```

- Connectors return `CommunicationMessage`. MIME/HTML/Gmail JSON/Graph JSON stay inside future vendor adapters.
- Pagination uses opaque `str | None` cursors. Adapters interpret them.
- Ingestion fetches one message, builds `CommunicationRequest`, and delegates. It does not call `AIProvider` or persist analyses.
- Identity remains on `CommunicationAnalysisWorkflowService`. `AUTH_MODE=disabled` continues to skip persistence when the workflow is constructed without a principal.

## Out of Scope (10A)

- Gmail and Microsoft Graph adapters
- OAuth, tokens, and connector account ownership
- Alembic migrations and connector tables
- API routes
- Raw-mail persistence
- Connector factory (connectors will later be per-user / per-account)

ADR-015 is deferred until Phase 10 final documentation or a focused connector architecture review.
