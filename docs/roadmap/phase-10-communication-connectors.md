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
- **10B is Completed:** `connector_accounts` persistence, user ownership isolation, opaque `credential_ref`, `ConnectorAccountService`, Alembic revision `10b0001`, SQLite and PostgreSQL tests. No OAuth, token storage, Gmail, Microsoft Graph, or connector API routes.
- **10C is implementation complete / review pending:** offline Gmail API v1 REST adapter, MIME normalization, mocked HTTP tests, and a mocked ingestion-boundary test. No OAuth, no real Gmail calls, no token persistence, no Gmail SDK, no connector HTTP routes.
- **10D is pending.**
- **10E is pending.**

Do not implement Microsoft Graph, OAuth, or connector API routes in 10C.

## Deliverables

- [x] Phase 10A — Connector Architecture & Domain Contracts (completed)
- [x] Phase 10B — Connector Accounts & Credential References (completed)
- [x] Phase 10C — Gmail Read-Only Adapter (implementation complete; review pending)
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

## Phase 10C Architecture

```text
Gmail API v1 REST (mocked HTTP in 10C)
        ↓
GmailCommunicationConnector (infrastructure.connectors.gmail)
        ↓
CommunicationMessage
        ↓
CommunicationIngestionService
        ↓
CommunicationAnalysisWorkflowService (existing)
```

- `GmailCommunicationConnector` implements the unchanged `CommunicationConnector` contract: `provider`, `list_messages(ConnectorMessageQuery) -> MessagePage`, `fetch_message(provider_message_id) -> CommunicationMessage`.
- Connector provider identity is `gmail`. Normalized messages still use `SourceType.EMAIL`. There is no `SourceType.GMAIL`.
- Direct REST against `https://gmail.googleapis.com/gmail/v1` with an injected `httpx.Client`. No `googleapiclient`, `google-auth`, or other Gmail SDK.
- The caller owns client lifecycle. Construction makes no network call.
- Access tokens are supplied in memory by `Callable[[], str]` (`AccessTokenProvider`). The adapter does not implement OAuth, refresh, PKCE, callbacks, secret-store lookup, or `credential_ref` resolution.
- 10B remains compatible: `provider="gmail"` plus opaque `external_account_id` and `credential_ref` can later compose with a credential resolver without schema changes. 10C does not call `ConnectorAccountService`.

### List and fetch

- List: `GET /users/me/messages` with `maxResults=query.limit` and `pageToken=query.cursor` only when a cursor is supplied. No `q`, `labelIds`, or `includeSpamTrash`.
- Gmail `messages.list` returns id stubs. Because `MessagePage.items` is `list[CommunicationMessage]`, list performs 1 list request plus N sequential `messages.get` fetches. This N+1 cost is accepted for the bounded Phase 10 MVP (`limit` already max 100). The domain contract is not redesigned in 10C.
- One `list_messages` call returns exactly one Gmail page. `nextPageToken` is copied unchanged to `MessagePage.next_cursor`. The adapter does not follow pagination automatically.
- Fetch: `GET /users/me/messages/{id}?format=full`. Provider message id is quoted into the path segment so a malicious id cannot change scheme, host, or query target. Redirects are not followed.
- Individual fetch failure fails the list operation. There is no retry, backoff, or concurrent fan-out.

### Normalization

- MIME traversal supports root `text/plain`, `multipart/alternative`, `multipart/mixed` with nested alternative, and recursive parts.
- Body preference: first non-empty `text/plain` in recursive MIME order, else first non-empty `text/html` converted with stdlib `html.parser.HTMLParser`. Multiple plain parts are not concatenated. Script/style content is dropped. `CommunicationMessage.body` never receives raw HTML.
- Attachments are ignored (non-empty `filename`, `Content-Disposition: attachment`, and/or `attachmentId` without inline `body.data`). `Content-Disposition: inline` is not treated as an attachment. Attachment endpoints are not called.
- Gmail `body.data` is base64url-decoded with restored padding. Malformed encoding becomes `ConnectorMessageContentError`.
- Headers are read case-insensitively. From/To/Cc/Bcc/Subject/Date use stdlib `email` utilities, including RFC 2047 decoding. Missing From is a content error; missing Subject is allowed. Missing To/Cc/Bcc yields an empty recipient list (allowed by `MessageMetadata`). Bcc is included when present. Duplicate recipient addresses are dropped, first-seen order preserved.
- `sent_at` prefers a valid RFC Date header, else `internalDate`. RFC Date values without a timezone are interpreted as UTC, not local time. `received_at` uses Gmail `internalDate` (milliseconds since epoch). Datetimes are timezone-aware UTC. Current time is never invented.
- `CommunicationMessage.message_id` and `MessageMetadata.source_id` are the Gmail API resource `id`. The fetch path uses the caller-supplied id; a successful Gmail body is trusted rather than compared for mismatch. `thread_id` is Gmail `threadId`. Existing `labels` metadata receives `labelIds` when present.
- Gmail `snippet` is never used as a body fallback. Empty textual content is `ConnectorMessageContentError`.

### Errors, logging, and privacy

- 401 → `ConnectorAuthenticationError`
- 403 → `ConnectorPermissionError`, except bounded Gmail reason codes `rateLimitExceeded`, `userRateLimitExceeded`, and `quotaExceeded` → `ConnectorRateLimitError`
- 404 on fetch → `ConnectorMessageNotFoundError`. List 404 is `ConnectorUnavailableError`, not message-not-found.
- 429 → `ConnectorRateLimitError`
- 5xx, timeout, and transport errors → `ConnectorUnavailableError`
- List `400` with a supplied cursor → `ConnectorInvalidCursorError`. This mapping is used because 10C list requests send only `maxResults` and optional `pageToken`. List `400` without a cursor is a generic `ConnectorError`, not an invalid cursor.
- Malformed MIME/base64/missing sender/empty body → `ConnectorMessageContentError`
- Malformed list envelopes or non-JSON success responses → `ConnectorUnavailableError`
- No retry for 401/403/429/5xx/timeout.
- Adapter logging is omitted; ingestion already emits `connector_fetch_started|completed|failed` with bounded fields (`provider`, `duration_ms`, `result_count`, `error_class`). Tokens, Authorization, subjects, senders, bodies, snippets, message ids, and page tokens are not logged.

### Out of scope for 10C

- OAuth consent, authorization-code exchange, PKCE, refresh-token storage, `token.json`
- Real Gmail API calls or Google Cloud Console mutations
- Token columns, Settings tokens, `.env` tokens, schema/migrations
- Connector HTTP/API routes, connector factory, credential resolver
- Attachments, sending, labels modification, webhooks, sync state, raw-message persistence
- Microsoft Graph
- Live mailbox verification

### Restricted Gmail scope note

Future live Gmail message-body access intends to use `https://www.googleapis.com/auth/gmail.readonly`. That scope is currently classified by Google as a restricted Gmail scope. Provider authorization and compliance requirements must be reviewed before production or public release. Phase 10C does not implement OAuth and does not claim Google production approval, OAuth verification, or a completed security assessment.

ADR-015 and credential-store ADRs remain deferred until Phase 10E or a focused connector architecture review.
