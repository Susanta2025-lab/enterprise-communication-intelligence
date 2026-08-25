# Phase 14 — Connected Mailbox Read and Analysis

## Objective

Expose the already-implemented mailbox connector/read path through a secure user-facing HTTP surface, and connect that path to the already-implemented AI analysis workflow.

```text
Authenticated ECI user
→ owned ACTIVE connector account
→ list recent messages (bounded)
→ select one provider message id
→ fetch through existing Gmail/Graph connector
→ CommunicationMessage
→ existing AI analysis workflow
→ structured analysis
→ optional existing analysis-history persistence
```

Phase 14 does **not** rebuild OAuth, connectors, AI analysis, workflow execution, or credential stores.

```text
Phase 14
= communications:read
  + bounded mailbox listing
  + connected-mailbox analyze HTTP
  + provider-neutral read connector factory

automatic replies
= still deferred
```

## Status

Phase 14 is **Completed**. Architecture is reconciled. **14A is Completed. 14B is Completed. 14C is Completed. 14D is Completed. 14E is Completed. 14F is Completed.**

- **14A is Completed:** `communications:read`, public list/analyze contract, mailbox-read error types, ADR-024.
- **14B is Completed:** provider-neutral `CommunicationConnectorFactory`, Gmail/Graph routing, lazy access tokens, read-side DI independent of `communications:send`.
- **14C is Completed:** mounted mailbox-backed analyze for an owned ACTIVE/read-capable account; direct-text analyze unchanged.
- **14D is Completed:** bounded mailbox listing through `GET /api/v1/connector-accounts/{id}/messages`, opaque cursor, Graph `nextLink` not exposed.
- **14E is Completed:** confirmed permanent OAuth refresh failure persists exact-owned `ACTIVE → REAUTH_REQUIRED` on list and analyze; transient failures and mailbox HTTP 401/403 do not mutate lifecycle; privacy sentinels stay out of responses and logs.
- **14F is Completed:** privacy-safe Gmail ID-token verification diagnostics retained as production observability; live Entra `communications:read` provisioning; local-runtime Gmail and Microsoft Graph bounded list → selected-message analyze with `MockAIProvider`; README/docs audit; full offline regression. That proof is not ACA-hosted or ECS-hosted Phase 14 mailbox→AI certification, and it did not call Foundry or Bedrock.

Phase 13 remains **Completed**, including a controlled local live Gmail disconnect → exact-account reauthorization (same connector row `eaae1e04-89a9-4c90-a2c1-f9036438de25`). That proof is not cloud-hosted ACA/ECS certification.

## Permission model

Introduce `communications:read`. Do not collapse mailbox OAuth lifecycle into mailbox-content authority.

| Permission | Meaning |
|---|---|
| `communications:connect` | Authorize, disconnect, and reauthorize mailbox delegation |
| `communications:read` | Retrieve content from an owned connected mailbox |
| `communications:analyze` | Run AI analysis |
| `communications:workflow` | Workflow proposal and approval |
| `communications:send` | Execute an external communication |

Recommended HTTP authorization:

- `GET /api/v1/connector-accounts/{connector_account_id}/messages` requires `communications:read`
- `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze` requires **both** `communications:read` and `communications:analyze`

Neither permission implies the other. `communications:connect` does not authorize mailbox listing or analyze. Direct-text `POST /api/v1/communications/analyze` continues to require `communications:analyze` only.

Phase 14A implements the code, test, and documentation foundation for `communications:read`. Live identity-provider scope provisioning was deferred until controlled Phase 14 live validation (14F). Do not modify live Entra configuration in 14A–14E. **14A is Completed.**

## Public API shape

Provider-neutral endpoints. Provider message identifiers stay opaque strings. Graph/Gmail path details do not enter the public contract.

```http
GET /api/v1/connector-accounts/{connector_account_id}/messages
```

```http
POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze
{
  "provider_message_id": "<opaque provider message id>"
}
```

`provider_message_id` is a JSON body field, not a path segment, so Graph/Gmail identifier encoding stays inside the adapters.

Analyze responses reuse the existing analysis contract (`CommunicationAnalysisResponse`). Listing responses are provider-neutral metadata only. Tokens, `credential_ref`, raw mailbox bodies, and provider pagination URLs are never returned.

## Bounded mailbox listing

Listing is in Phase 14 so a caller can select a message, then analyze it. It is not mailbox synchronization.

In scope:

- recent messages from an owned `ACTIVE` account
- bounded page size
- provider-neutral metadata (for example provider message id, subject, sender, timestamps)
- provider-neutral opaque pagination cursor
- `communications:read`

Out of listing scope:

- provider `nextLink` or other vendor pagination URLs in the public API
- local mailbox mirror
- background synchronization, workers, or webhooks
- search
- attachments
- bulk analysis
- inbox-wide summarization
- returning full message bodies on the list endpoint

Current Gmail/Graph `list_messages` adapters may hydrate full messages internally. The public list contract still returns metadata only. Graph continuation must be wrapped as an ECI-opaque cursor before it leaves the application.

## Application orchestration

Keep business orchestration out of FastAPI handlers.

```text
HTTP
→ auth (read, or read + analyze)
→ ownership / ACTIVE / mail.read / supported provider
→ CommunicationConnectorFactory
→ delegated credential resolution
→ provider read
→ CommunicationMessage (analyze path)
→ CommunicationIngestionService
→ CommunicationAnalysisWorkflowService
→ optional AnalysisHistoryService
```

`CommunicationConnector` remains read-only. `CommunicationActionExecutor` remains the write boundary. No automatic replies.

`CommunicationConnectorFactory` is the missing provider-neutral read-routing port, analogous to `CommunicationActionExecutorFactory`. Do not merge read and write factories.

Permanent refresh `invalid_grant` on the read path reuses application-level `REAUTH_REQUIRED` for the exact owned account. The credential resolver does not persist connector-account status.

No Alembic revision is required. Existing `analyses.connector_account_id` and `analyses.message_id` already provide mailbox provenance for later workflow proposal/execute.

## Documentation policy

The final Phase 14 documentation slice (14F) inspected and updated every relevant README whose current-state description changed, including the root `README.md`.

Historical Azure/AWS runbooks in `deployment/azure/` and `deployment/aws/` remain historical and must not claim cloud-hosted Phase 14 certification of the retained ACA/ECS deployments.

## Planned slices

### 14A — Read Authorization + Public Contract

**14A is Completed.**

Objective: introduce `communications:read`, freeze the public list/analyze contract, and map ownership/lifecycle failures without provider HTTP.

Implementation surface: permission constant and FastAPI dependency, request/response schemas, application exceptions and HTTP handlers, tests that connect does not imply read and read does not imply analyze.

Migration: none.

Docs: route/schema docs only as needed for the contract. Live Entra scope provisioning is not part of 14A.

Live validation: no.

Exit: contract and authorization tests pass; no Gmail/Graph HTTP required.

### 14B — Provider-Neutral Read Connector Factory

**14B is Completed.**

Objective: route an already-owned `ConnectorAccountRecord` to `GmailCommunicationConnector` or `MicrosoftGraphCommunicationConnector`.

Implementation surface: `CommunicationConnectorFactory` / `ProviderCommunicationConnectorFactory`; read-gated DI for credential resolver and HTTP client; preserve `CommunicationCredentialReauthorizationRequiredError` on the read token path. Access-token acquisition remains lazy. The factory does not check ownership, ACTIVE status, or `mail.read`.

Migration: none.

Docs: phase roadmap plus architecture/dependency-flow updates for the read factory boundary.

Live validation: no.

Exit: factory tests pass; `CommunicationConnector` remains distinct from `CommunicationActionExecutor`. No mailbox list/analyze routes mounted.

### 14C — Connected Message → AI Analysis

**14C is Completed.**

Objective: owned `ACTIVE` mailbox message → existing ingestion → AI analysis → optional history.

Implementation surface: `ConnectedMailboxAnalysisService`, mounted `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze`, Gmail/Graph fake-HTTP integration, `MockAIProvider`. Ownership and mailbox usability are established before credential I/O, mailbox HTTP, or AI. Existing `CommunicationIngestionService` and `CommunicationAnalysisWorkflowService` are reused. Confirmed permanent refresh failure on this path now persists `ACTIVE → REAUTH_REQUIRED` for the exact owned account (14E).

Migration: none.

Docs: OpenAPI and API docs distinguish direct-text analyze from connected-mailbox analyze. Listing remains undocumented as served.

Live validation: no.

Exit: offline analyze path green; direct-text `POST /api/v1/communications/analyze` unchanged.

### 14D — Bounded Mailbox Message Listing

**14D is Completed.**

Objective: list recent messages as provider-neutral metadata with an opaque cursor.

Implementation surface: `ConnectedMailboxMessageListingService`, mounted `GET /api/v1/connector-accounts/{connector_account_id}/messages`, reuse of Phase 14A list schemas and Phase 14B `CommunicationConnectorFactory`, reuse of existing `CommunicationConnector.list_messages`. Graph `@odata.nextLink` is normalized inside the Graph adapter into an opaque pagination token; the public `next_cursor` is never a Graph URL. Listing is a bounded request/response read-through: no sync, local mirror, search, attachments, AI, persistence of mailbox messages, workflow actions, or send/reply.

Migration: none.

Docs: OpenAPI and API docs for the list route. Connected-mailbox product flow is list → select → analyze.

Live validation: no.

Exit: listing is bounded, provider-neutral, and does not add sync/search/attachments.

### 14E — Lifecycle / Privacy / Failure Hardening

**14E is Completed.**

Objective: DISCONNECTED / `REAUTH_REQUIRED` / missing `mail.read` / permanent vs transient refresh / sanitization.

Implementation surface: shared `persist_mailbox_reauthorization_required` on listing and analyze; confirmed permanent refresh (`CommunicationCredentialReauthorizationRequiredError`) persists exact-owned `ACTIVE → REAUTH_REQUIRED` while preserving `credential_ref`, `granted_capabilities`, and `external_account_id`; transient store/refresh and mailbox HTTP 401/403 after a valid token leave the account `ACTIVE`; ownership-safe CAS via existing `mark_reauth_required_owned`; privacy sentinel tests.

Migration: none.

Docs: 14E lifecycle/privacy notes in API, application-layer, sequence, and ADR-023/024 consequences. Root README sweep was completed in 14F.

Live validation: no.

Exit: owned unusable accounts do not leak cross-user existence; confirmed permanent refresh blocks further mailbox I/O until explicit reauthorization; tokens and bodies stay out of responses and logs.

### 14F — Final Documentation, Observability, Live Validation & Regression

**14F is Completed.**

Objective: retain production-safe Gmail OAuth observability from live investigation, complete controlled local-runtime live proof, reconcile current-state documentation, and close Phase 14 with full offline regression.

Implementation surface:

- Privacy-safe Gmail ID-token verification diagnostics in `GoogleMailboxOAuthClient`. Verification remains `google.oauth2.id_token.verify_oauth2_token(token, Request(), audience=client_id)` (signature, issuer, audience, expiry). `sub` remains required from verified claims and must still match the bound connector identity on reauthorization. Failure logs record `provider=gmail`, `operation=verify_id_token`, `verify_error_class` (exception class name only), `subject_present`, and `issuer_present` / `audience_present` only from already-verified claims, plus allowlisted token-exchange presence flags (`oauth_error`, `refresh_token_present`, `id_token_present`). Token, claim, and credential values are not logged. The public callback remains `400 {"detail":"Mailbox authorization failed."}`.
- Live Entra provisioning of `communications:read` alongside the previous four ECI delegated permissions. The verifier was updated to all five scopes. Fresh real ECI OIDC tokens were used.
- Local-runtime Gmail and Microsoft Graph exact-account reauthorization, bounded `GET .../messages`, selected-message `POST .../messages/analyze` with `MockAIProvider`, and provenance checks. No Foundry or Bedrock inference. No send/reply. No `WorkflowAction`.
- README/docs audit including root `README.md`. Historical Azure/AWS runbooks remain historical.

Migration: none.

Docs: current-phase docs plus README audit. Deployment runbooks stay historical.

Live validation: completed as a controlled local-runtime operator step. Recorded sanitized evidence:

- `communications:read` provisioned in live Entra; previous four ECI scope identifiers preserved; verifier updated to all five scopes; fresh real ECI OIDC tokens used
- Gmail exact-account reauthorization succeeded; same connector and external identity preserved; bounded GET messages passed; optional one-page continuation passed where exercised; selected-message analyze passed with `MockAIProvider`; provenance verified; no raw body persistence; no `WorkflowAction` / send; connector remained `ACTIVE`
- Microsoft Graph exact-account reauthorization succeeded; same connector and identity preserved; bounded GET messages with `page_size=1` passed; one continuation passed; raw `@odata.nextLink` not exposed; selected-message analyze passed with `MockAIProvider`; provenance verified; no raw body persistence; no `WorkflowAction` / send; connector remained `ACTIVE`
- Local ECI runtime + local PostgreSQL. Not ACA-hosted or ECS-hosted Phase 14 mailbox→AI certification. Not Foundry or Bedrock live inference.

Mailbox addresses, message ids, sender, subject, body, tokens, external identity values, and credential locators are not recorded.

Exit: docs match implemented behavior; no cloud-hosted Phase 14 certification claim; `pip check`, `ruff`, and pytest pass.

## Out of scope

- Mailbox search, attachments, bulk analysis, inbox-wide summarization
- Background sync, webhooks, local mirror, scheduled polling
- Automatic replies, workflow proposal/approval/execute as part of this phase
- Streaming AI, frontend/mobile UI
- New cloud resources, managed PostgreSQL, ACA/ECS Phase 14 mailbox→AI certification, Foundry/Bedrock live inference for this flow
- Alembic schema changes

## Cloud implications

Repository architecture needs no new Azure or AWS resources. Existing PostgreSQL, Key Vault / Secrets Manager permissions, and OAuth redirects remain the runtime baseline. Image update only.

Phase 14F validated local ECI runtime + real Entra OIDC + real Gmail delegated mailbox + real Microsoft Graph delegated mailbox + local PostgreSQL + `MockAIProvider`. It did not certify ACA-hosted or ECS-hosted Phase 14 mailbox→AI, and it did not call Foundry or Bedrock. Historical runbooks must not claim that certification.
