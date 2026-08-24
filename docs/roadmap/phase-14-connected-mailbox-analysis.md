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

Phase 14 is **Next**. Architecture is reconciled. **14A is Completed. 14B is Completed. 14C is Completed. 14D is Completed.** Remaining slices are 14E–14F.

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

Phase 14A implements the code, test, and documentation foundation for `communications:read`. Live identity-provider scope provisioning is deferred until controlled Phase 14 live validation. Do not modify live Entra configuration in 14A–14E. **14A is Completed.**

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

The final Phase 14 documentation slice (14F) **must** inspect and update every relevant README whose current-state description changed, including the root `README.md`.

Do not skip README updates. Historical Azure/AWS runbooks in `deployment/azure/` and `deployment/aws/` remain historical and must not claim cloud-hosted Phase 14 certification of the retained ACA/ECS deployments.

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

Implementation surface: `ConnectedMailboxAnalysisService`, mounted `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze`, Gmail/Graph fake-HTTP integration, `MockAIProvider`. Ownership and mailbox usability are established before credential I/O, mailbox HTTP, or AI. Existing `CommunicationIngestionService` and `CommunicationAnalysisWorkflowService` are reused. Durable `ACTIVE → REAUTH_REQUIRED` mutation on confirmed refresh failure remains 14E.

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

Objective: DISCONNECTED / `REAUTH_REQUIRED` / missing `mail.read` / permanent vs transient refresh / sanitization.

Implementation surface: failure matrix, `mark_reauth_required_owned` on confirmed read-path `invalid_grant`, privacy tests.

Migration: none.

Docs: none until 14F.

Live validation: no.

Exit: owned unusable accounts do not leak cross-user existence; tokens and bodies stay out of responses and logs.

### 14F — Live Validation + Documentation + Regression

Objective: controlled live proof, README/docs audit, full offline regression.

Implementation surface: Phase 14 roadmap completion, API/architecture/cloud docs, ADR if the public read/analysis boundary is recorded as ADR-024, **all relevant README files including root README**.

Migration: none.

Docs: current-phase docs plus README audit. Deployment runbooks stay historical.

Live validation: yes, after implementation, as a separate controlled operator step. Prefer real owned mailbox + `MockAIProvider` for Gmail and Microsoft, then an optional separate AI-provider proof. No send. Live IdP `communications:read` scope provisioning belongs here if that proof uses real OIDC.

Exit: docs match implemented behavior; no cloud-hosted Phase 14 certification claim; `pip check`, `ruff`, and pytest pass.

## Out of scope

- Mailbox search, attachments, bulk analysis, inbox-wide summarization
- Background sync, webhooks, local mirror, scheduled polling
- Automatic replies, workflow proposal/approval/execute as part of this phase
- Streaming AI, frontend/mobile UI
- New cloud resources, managed PostgreSQL, live Entra changes before 14F
- Alembic schema changes

## Cloud implications

Repository architecture needs no new Azure or AWS resources. Existing PostgreSQL, Key Vault / Secrets Manager permissions, and OAuth redirects remain the runtime baseline. Image update only.

Cloud-hosted certification of retained ACA/ECS deployments is not a Phase 14 architecture requirement and must not be claimed by historical runbooks.
