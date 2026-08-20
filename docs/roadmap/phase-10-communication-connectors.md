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
- **10C is Completed:** mocked/offline tests plus a controlled local live verification passed. The repository still contains only the Gmail API v1 REST adapter, MIME normalization, mocked HTTP tests, and a mocked ingestion-boundary test. No OAuth implementation, token persistence, Gmail SDK, or connector HTTP routes were added to ECI. The live mailbox check was a separate local verification, not GitHub Actions.
- **10D is pending.**
- **10E is pending.**

Phase 10 overall remains in progress. Phase 10D (Microsoft Graph Read-Only Adapter) may now begin; it is not implemented in this checkpoint.

## Deliverables

- [x] Phase 10A — Connector Architecture & Domain Contracts (completed)
- [x] Phase 10B — Connector Accounts & Credential References (completed)
- [x] Phase 10C — Gmail Read-Only Adapter (mocked/offline tests + controlled local live verification passed)
- [ ] Phase 10D — Microsoft Graph Read-Only Adapter (pending)
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
Gmail API v1 REST
        ↓
GmailCommunicationConnector (infrastructure.connectors.gmail)
        ↓
CommunicationMessage
        ↓
CommunicationIngestionService
        ↓
CommunicationAnalysisWorkflowService (existing)
```

The designed path above is unchanged. Offline tests mock HTTP and cover request construction through the ingestion-boundary test. The controlled local live verification on 2026-08-20 exercised only:

```text
Gmail API v1 REST
        ↓
GmailCommunicationConnector
        ↓
CommunicationMessage
        STOP
```

The remaining workflow was already covered by offline integration testing and was deliberately excluded from the live mailbox test.

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

### Out of scope for 10C implementation

The 10C adapter in ECI still does not include:

- OAuth consent, token exchange, PKCE, or durable token files inside ECI
- Token columns, Settings tokens, `.env` tokens, schema/migrations
- Connector HTTP/API routes, connector factory, credential resolver
- Attachments, sending, labels modification, webhooks, sync state, raw-message persistence
- Microsoft Graph

A controlled local live verification was performed after 10C implementation. It did not add OAuth or credentials to ECI. See [Controlled Live Gmail Verification](#controlled-live-gmail-verification).

### Restricted Gmail scope note

`https://www.googleapis.com/auth/gmail.readonly` is currently treated as a restricted Gmail scope. The controlled local live verification does not constitute Google app verification, production authorization approval, restricted-scope compliance approval, or security-assessment completion. Future production or public use must separately evaluate Google's then-current authorization, verification, and restricted-scope requirements. Phase 10C does not add OAuth to ECI and does not make legal or compliance guarantees.

ADR-015 and credential-store ADRs remain deferred until Phase 10E or a focused connector architecture review.

## Controlled Live Gmail Verification

After Phase 10C implementation, focused review, commit, push, and green CI, a controlled local live verification was performed against the real Gmail API on **2026-08-20**.

This is a verification checkpoint, not a new architecture decision. No ADR is recorded for it.

### Verification boundary

The live flow was:

```text
Google OAuth Desktop authorization
        ↓
temporary local OAuth credentials
        ↓
Gmail API v1
        ↓
GmailCommunicationConnector
        ↓
CommunicationMessage
        STOP
```

The live verification intentionally stopped at the connector/domain boundary. It did not continue into `CommunicationIngestionService`, `CommunicationAnalysisWorkflowService`, `AIProvider`, `MockAIProvider`, Microsoft Foundry, Amazon Bedrock, PostgreSQL, analysis persistence, or cloud deployment.

### Authentication setup

Non-secret architectural facts only:

- Gmail API was enabled in a dedicated Google Cloud development project.
- Google Auth Platform was configured for External testing.
- One authorized test user was used.
- A Desktop OAuth client was used only for local verification.
- The requested scope was exactly `https://www.googleapis.com/auth/gmail.readonly`.
- OAuth credentials were handled only in a temporary local workspace outside the ECI repository.
- No OAuth credentials were committed to Git.
- No OAuth implementation was added to ECI.

### Temporary local workspace

A temporary local workspace outside the repository was used for OAuth authorization and live verification. Conceptual files in that external workspace included `credentials.json`, `token.json`, an authorization helper script, and a verification helper script. None of those files are part of the ECI repository, and they were not added by this checkpoint.

### Live test design

The verification used the real committed `GmailCommunicationConnector` with:

- a real `httpx.Client`
- a temporary in-memory access-token callable
- `ConnectorMessageQuery(limit=1)`

The test intentionally requested only one Gmail list page and one message. Expected network pattern:

1. 1 × Gmail `users.messages.list`
2. 1 × Gmail `users.messages.get`

No automatic pagination. No attachment request. No additional Gmail API operations.

### Synthetic test message

A synthetic test message was placed in the authorized mailbox before verification. It contained no meaningful personal or business data. The live script did not print message content.

### Successful verification result

Validated outcomes:

- Google OAuth authorization succeeded
- `gmail.readonly` authorization succeeded
- Gmail API authentication succeeded
- real `users.messages.list` succeeded
- real `users.messages.get` succeeded
- `GmailCommunicationConnector` successfully normalized the Gmail message
- exactly one `CommunicationMessage` was produced
- normalized `source_type == SourceType.EMAIL`
- normalized body was non-empty
- message content was not printed by the verification script

Terminal result:

```text
Live Gmail connector verification: PASS
```

No credentials or mailbox content are recorded here.

### What this proves

Phase 10C has now been validated at two levels.

**Automated/offline verification.** `MockTransport`-based tests prove request construction, one-page pagination, message fetching, MIME traversal, HTML fallback, attachment exclusion, header normalization, timestamp mapping, error mapping, privacy boundaries, and the ingestion boundary.

**Controlled live verification.** Real Gmail API verification proves:

- Google OAuth credentials can supply the adapter's existing in-memory token interface
- the committed adapter can authenticate to the real Gmail API
- the real Gmail list endpoint is compatible with the adapter
- the real Gmail message fetch endpoint is compatible with the adapter
- a real Gmail `format=full` response can be normalized into the existing ECI `CommunicationMessage` model

This checkpoint does not claim more than those facts.

### What is not proven

The live test does not prove or implement:

- production OAuth lifecycle
- OAuth callback API routes
- refresh-token management inside ECI
- credential resolver integration
- secret-manager integration
- connector-account → credential_ref → credential resolver composition
- production Gmail onboarding
- multi-user Gmail OAuth management
- Gmail synchronization/history API
- background synchronization
- webhook/push notifications
- attachments
- Gmail send/modify/delete
- production restricted-scope verification
- Google security assessment completion
- AI analysis of live Gmail content, including Microsoft Foundry, Amazon Bedrock, and `MockAIProvider`
- persistence of live Gmail-derived analyses
- live multi-page Gmail pagination or N+1 fetch behavior at scale
- live Gmail error paths (`401`/`403`/`404`/`429`/`5xx`, timeouts, invalid cursors)
- large mailboxes, large messages, or exhaustive MIME/label/quota coverage
- Azure-hosted Gmail OAuth
- AWS-hosted Gmail OAuth

### Privacy and data minimization

- Raw Gmail JSON/MIME existed only transiently during the request.
- The live verification did not persist the fetched Gmail message. The designed workflow may persist derived analysis later; that path was not exercised live.
- No Gmail message content was sent to Microsoft Foundry, Amazon Bedrock, or `MockAIProvider`.
- No Gmail message content was written to PostgreSQL.
- No Gmail message content was intentionally logged.
- No OAuth token was intentionally logged.
- Verification output contained only bounded pass/fail metadata.

These statements describe the verification procedure and the adapter's existing bounded logging. They are not stronger guarantees than the implementation supports.

### Implementation CI checkpoint

Phase 10C implementation commit:

- `2f79840` — `feat: add Gmail read-only connector`
- GitHub Actions run `32351444028`
- Result: PASS

The controlled local live verification did not run in GitHub Actions. It was a separate local verification. CI proves the mocked/offline suite for that commit; it does not prove the live mailbox check.

## Phase 10D Readiness

Phase 10D may now begin: Microsoft Graph Read-Only Adapter. It should remain a sibling infrastructure adapter implementing the unchanged `CommunicationConnector` contract. Phase 10D is not implemented in this documentation checkpoint.
