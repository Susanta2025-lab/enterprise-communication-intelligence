# Phase 10 — Communication Connectors

## Objective

Introduce a vendor-neutral communication connector boundary so external adapters can supply already-normalized `CommunicationMessage` values to the existing analysis workflow, and persist user-owned connector accounts with opaque credential references — without Gmail/Graph SDKs, OAuth, token storage, or connector API routes.

## Business Value

- Proves the path: external adapter → `CommunicationConnector` → `CommunicationIngestionService` → `CommunicationAnalysisWorkflowService`.
- Keeps email as a `SourceType` medium. Vendor identity stays out of the domain enum.
- Keeps AI analysis, persistence, and HTTP outside connector adapters.
- Binds authenticated ECI users to internal `users.id` and user-owned connector accounts without storing OAuth tokens.

## Status

Phase 10 is **In progress**.

- **10A is Completed:** domain connector contract, connector-neutral errors, ingestion service, offline fake adapter, unit and boundary tests. No API, OAuth, or vendor SDKs.
- **10B is implementation complete / review pending:** `connector_accounts` persistence, user ownership isolation, opaque `credential_ref`, `ConnectorAccountService`, Alembic revision `10b0001`, SQLite and PostgreSQL tests. No OAuth, token storage, Gmail, Microsoft Graph, or connector API routes.
- **10C is pending.**
- **10D is pending.**
- **10E is pending.**

Do not implement Gmail, Microsoft Graph, OAuth, or connector API routes in 10B.

## Deliverables

- [x] Phase 10A — Connector Architecture & Domain Contracts (completed)
- [x] Phase 10B — Connector Accounts & Credential References (implementation complete; review pending)
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

## Phase 10B Architecture

```text
AuthenticatedPrincipal
        ↓
IdentityResolver
        ↓
ConnectorAccountService
        ↓
PersistenceUnitOfWork
        ↓
ConnectorAccountRepository
        ↓
connector_accounts
```

Future (not implemented in 10B):

```text
connector account → credential resolver → CommunicationConnector → CommunicationIngestionService
```

- `connector_accounts` is the only new table. There is no `connector_credentials` table and no token blob.
- `credential_ref` is an opaque locator for credential material stored elsewhere. It is not an access token, refresh token, authorization code, client secret, JWT, or Authorization header.
- Application-facing `ConnectorAccountResult` omits `user_id` and `credential_ref`.
- Ownership is enforced in SQL (`connector_account_id` AND `user_id`). Cross-user and unknown resources are indistinguishable.
- Disconnect is a soft status change (`disconnected`) that nulls `credential_ref` and retains the account identity for reconnect. Repeated disconnect of an owned row is safe: status stays `disconnected`, `credential_ref` stays null, and `updated_at` is written because the owned UPDATE is unconditional.
- Registration is idempotent for `(user_id, provider, external_account_id)`. Concurrent first registration uses the unique constraint, rolls back the failed unit of work, and re-reads the winner on a fresh unit of work.
- Re-registering an already-active logical account returns the existing row and does not replace `credential_ref`. Locator rotation is out of scope for 10B; disconnect then register is the supported way to supply a new locator, including an explicit null.
- `register(..., credential_ref=None)` cannot distinguish an omitted argument from an explicit null. Both mean "no locator". New rows store null. Reactivation replaces the stored locator with the supplied value, including null.
- Identity resolution commits separately from connector-account writes. Future OAuth must stay outside long database transactions.
- No Gmail adapter, Microsoft Graph adapter, OAuth exchange, credential resolver, sync state, raw-message persistence, or connector HTTP routes.

ADR-015 and credential-store ADRs remain deferred until Phase 10E or a focused connector architecture review.
