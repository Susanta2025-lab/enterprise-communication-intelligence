# Phase 10 — Communication Connectors

## Objective

Introduce a vendor-neutral communication connector boundary so external adapters can supply already-normalized `CommunicationMessage` values to the existing analysis workflow, and persist user-owned connector accounts with opaque credential references — without Gmail/Graph SDKs, OAuth, token storage, or connector API routes.

## Business Value

- Proves the path: external adapter → `CommunicationConnector` → `CommunicationIngestionService` → `CommunicationAnalysisWorkflowService`.
- Keeps email as a `SourceType` medium. Vendor identity stays out of the domain enum.
- Keeps AI analysis, persistence, and HTTP outside connector adapters.
- Binds authenticated ECI users to internal `users.id` and user-owned connector accounts without storing OAuth tokens.

## Status

Phase 10 is **Completed**.

- **10A is Completed:** domain connector contract, connector-neutral errors, ingestion service, offline fake adapter, unit and boundary tests. No API, OAuth, or vendor SDKs.
- **10B is Completed:** `connector_accounts` persistence, user ownership isolation, opaque `credential_ref`, `ConnectorAccountService`, Alembic revision `10b0001`, SQLite and PostgreSQL tests. No OAuth, token storage, or connector API routes.
- **10C is Completed:** mocked/offline tests plus a controlled local live verification passed. The repository still contains only the Gmail API v1 REST adapter, MIME normalization, mocked HTTP tests, and a mocked ingestion-boundary test. No OAuth implementation, token persistence, Gmail SDK, or connector HTTP routes were added to ECI. The live mailbox check was a separate local verification, not GitHub Actions.
- **10D is Completed:** mocked/offline tests plus a controlled local live Microsoft Graph verification passed. The repository still contains only the Microsoft Graph REST v1.0 adapter, JSON normalization, nextLink validation, mocked HTTP tests, and a mocked ingestion-boundary test. No OAuth implementation, token persistence, Graph SDK, MSAL, or connector HTTP routes were added to ECI. The live Graph check was a separate local verification, not GitHub Actions.
- **10E is Completed:** architecture consistency review, shared documentation alignment, and full offline regression. No application code, runtime dependencies, or new tests.

Phase 10 overall is completed. Next: Phase 11 — Workflow Automation.

## Deliverables

- [x] Phase 10A — Connector Architecture & Domain Contracts (completed)
- [x] Phase 10B — Connector Accounts & Credential References (completed)
- [x] Phase 10C — Gmail Read-Only Adapter (mocked/offline tests + controlled local live verification passed)
- [x] Phase 10D — Microsoft Graph Read-Only Adapter (mocked/offline tests + controlled local live Microsoft Graph verification passed)
- [x] Phase 10E — Documentation finalization and Phase 10 closure (completed)

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

ADR-015 and credential-store ADRs remain deferred until a focused connector architecture review. Phase 10E did not create them.

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

## Phase 10D Architecture

```text
Microsoft Graph REST v1.0
        ↓
MicrosoftGraphCommunicationConnector (infrastructure.connectors.microsoft_graph)
        ↓
CommunicationMessage
        ↓
CommunicationIngestionService
        ↓
CommunicationAnalysisWorkflowService (existing)
```

The designed path above is unchanged. Offline tests mock HTTP and cover request construction through the ingestion-boundary test. The controlled local live verification on 2026-08-20 exercised only:

```text
Microsoft Graph REST v1.0
        ↓
MicrosoftGraphCommunicationConnector
        ↓
CommunicationMessage
        STOP
```

The remaining workflow was already covered by offline integration testing and was deliberately excluded from the live Graph test.

- `MicrosoftGraphCommunicationConnector` is a sibling of `GmailCommunicationConnector`. It implements the unchanged `CommunicationConnector` contract: `provider`, `list_messages(ConnectorMessageQuery) -> MessagePage`, `fetch_message(provider_message_id) -> CommunicationMessage`.
- Connector provider identity is `microsoft_graph`. Normalized messages still use `SourceType.EMAIL`. There is no `SourceType.OUTLOOK`, `SourceType.GRAPH`, or `SourceType.MICROSOFT`.
- Direct REST against `https://graph.microsoft.com/v1.0` with an injected `httpx.Client`. No Microsoft Graph SDK, MSAL, or Azure Identity inside this adapter.
- The caller owns client lifecycle. Construction makes no network call.
- Access tokens are supplied in memory by `Callable[[], str]` (`AccessTokenProvider`). The adapter does not implement OAuth, refresh, PKCE, callbacks, secret-store lookup, or `credential_ref` resolution.
- 10B remains compatible: `provider="microsoft_graph"` plus opaque `external_account_id` and `credential_ref` can later compose with a credential resolver without schema changes. 10D does not call `ConnectorAccountService`.
- Existing Phase 8 Entra apps (`eci-api-auth-dev`, `eci-auth-verifier-dev`, `eci-github-deploy-dev`, runtime managed identities) are not reused for Graph mailbox OAuth. A dedicated development-verification app registration was used only for the controlled live checkpoint; it is not the production OAuth architecture. See [Controlled Live Microsoft Graph Verification](#controlled-live-microsoft-graph-verification).

### Authorization context

Delegated Microsoft Graph permission used by the controlled live verification:

- `Mail.Read` — required because ECI analyzes message bodies.
- `Mail.ReadBasic` remains insufficient: it excludes `body` / `bodyPreview` / attachments.

10D does not implement consent, OAuth, or a production Entra app registration inside ECI. Successful personal-Microsoft-account user consent in this test does not mean admin consent is universally unnecessary, that all Microsoft tenants permit user consent, or that production consent architecture is complete. `Mail.ReadWrite`, `Mail.Send`, `Mail.ReadWrite.Shared`, and application `Mail.Read` remain out of scope.

### List and fetch

- List: `GET /v1.0/me/messages` with `$top=query.limit` and `$select=id`. No `$filter`, `$orderby`, `$search`, folder, read-state, sender, or date filtering.
- The mailbox is the signed-in user (`/me`). Shared and `/users/{id}` mailboxes are out of scope.
- Graph collection pages return id stubs. Because `MessagePage.items` is `list[CommunicationMessage]`, list performs 1 collection request plus N sequential `GET /me/messages/{id}` fetches. This N+1 cost is accepted for the bounded Phase 10 MVP (`limit` already max 100).
- One `list_messages` call returns exactly one Graph page. The adapter does not follow `@odata.nextLink` automatically.
- Fetch: `GET /v1.0/me/messages/{id}` with `$select` limited to `id`, `conversationId`, `subject`, `body`, `from`, `sender`, `toRecipients`, `ccRecipients`, `bccRecipients`, `sentDateTime`, `receivedDateTime`, `categories`. Provider message id is quoted into the path segment so a malicious id cannot change scheme, host, or query target. Redirects are not followed.
- Fetch sends `Prefer: outlook.body-content-type="text"` so Graph can return `body.contentType=text`.
- Individual fetch failure fails the list operation. There is no retry, backoff, batching, or concurrent fan-out.

### Pagination

- Graph `@odata.nextLink` is copied unchanged to `MessagePage.next_cursor`. The domain cursor remains opaque.
- A subsequent `ConnectorMessageQuery(cursor=next_link)` GETs that complete URL. `$top` / `$select` / `query.limit` are not rewritten onto the continuation. `$skip` and `$skiptoken` are not parsed or incremented.
- Because the bearer token is attached to every request, a cursor is validated before HTTP and before token resolution. Accepted nextLinks must be `https`, host `graph.microsoft.com`, no userinfo, no unexpected port, no fragment, and path `/v1.0/me/messages` (optional trailing slash). Other hosts, `http`, `/users/...`, `/me/drive`, `/beta`, relative URLs, and scheme-relative URLs become `ConnectorInvalidCursorError` with zero HTTP calls and zero token-provider calls.
- Hostname comparison is case-insensitive, so `https://GRAPH.MICROSOFT.COM/v1.0/me/messages` is accepted. `urlparse`/`httpx` may emit the canonical lowercase host on the request.
- Port `443` is accepted in addition to the omitted default HTTPS port. `httpx` may omit `:443` from the request URL. Other ports are rejected. A trailing-dot hostname (`graph.microsoft.com.`) is rejected.
- Path comparison uses the parsed path without decoding `%2F`/`%2e` or resolving `..`. Encoded separators, `..` segments, and `/v1.0/me/messages/anything` are rejected. The original cursor string is then sent unchanged so the query remains opaque (percent encoding and parameter order are not rewritten by the adapter).
- The full nextLink is not logged, persisted, or included in exception text.

### Normalization

- Graph JSON is normalized directly. `GET /me/messages/{id}/$value` (MIME) is not used.
- Text `body.content` maps to `CommunicationMessage.body`. HTML `contentType` is converted with the existing stdlib `html_to_plain_text` helper. `contentType` comparison is case-insensitive for `text` and `html` only; unknown values remain a content error. Script/style content is dropped. `CommunicationMessage.body` never receives raw HTML. Empty visible text is `ConnectorMessageContentError`.
- `bodyPreview` is never used as a body fallback. It is partial and must not be analyzed.
- Sender prefers Graph `from.emailAddress.address`. When `from` is missing or unusable, `sender.emailAddress.address` is a narrow fallback for delegate/send-as scenarios. Display names are ignored. Neither usable address is a content error.
- Recipients combine `toRecipients`, then `ccRecipients`, then `bccRecipients`. Display names are ignored. Blank/malformed addresses are skipped. Duplicates are dropped, first-seen order preserved. An empty recipient list is valid.
- Blank/whitespace/missing `subject` is `None`. No synthetic `(no subject)`. Non-string subject is treated as missing (`None`).
- `sentDateTime` → `sent_at`, `receivedDateTime` → `received_at`. ISO-8601 values including `Z` and explicit offsets become timezone-aware UTC. Naive values are interpreted as UTC, not local time. Missing/malformed timestamps are `None`. Current time is never invented.
- `CommunicationMessage.message_id` and `MessageMetadata.source_id` are the Graph message resource `id`, not `internetMessageId`. `thread_id` is `conversationId` when present.
- Graph `categories` map to existing `MessageMetadata.labels` when they are non-empty strings. Malformed entries are skipped.
- Attachments are ignored: they are not selected, downloaded, or parsed.

### Errors, logging, and privacy

- 401 → `ConnectorAuthenticationError`
- 403 → `ConnectorPermissionError`
- 404 on fetch → `ConnectorMessageNotFoundError`. List 404, including continuation 404, is `ConnectorUnavailableError`, not message-not-found.
- 429 → `ConnectorRateLimitError`. No retry, sleep, or `Retry-After` handling.
- 5xx, timeout, and transport errors → `ConnectorUnavailableError`
- List `400` with a supplied cursor → `ConnectorInvalidCursorError`. Locally rejected unsafe cursors also use this error before HTTP. List `400` without a cursor is a generic `ConnectorError`.
- Unexpected 3xx, including `302` to another host, is a generic `ConnectorError`. Redirects are not followed, so the bearer token is not forwarded.
- Malformed Graph JSON bodies / missing sender / empty body / unknown `contentType` → `ConnectorMessageContentError`
- Malformed list envelopes or non-JSON success responses → `ConnectorUnavailableError`
- Graph `error.message`, `innerError`, and request ids are not copied into exceptions or logs.
- No retry for 401/403/429/5xx/timeout.
- Adapter logging is omitted; ingestion already emits `connector_fetch_started|completed|failed` with bounded fields (`provider`, `duration_ms`, `result_count`, `error_class`). Tokens, Authorization, subjects, senders, bodies, message ids, conversation ids, categories, Graph JSON, and nextLinks are not logged.
- Raw Graph JSON exists only in memory during the request, is normalized immediately, and is not written to filesystem, database, or cache.

### Out of scope for 10D implementation

The 10D adapter in ECI still does not include:

- OAuth consent, token exchange, PKCE, or durable token files inside ECI
- Token columns, Settings tokens, `.env` tokens, schema/migrations
- Connector-account composition or credential resolver
- Shared/delegated mailboxes, application permissions, `/users/{id}`
- Attachments, MIME `$value`, send, modify, delete
- Webhooks, delta query, background sync, raw-message persistence
- Connector HTTP/API routes, connector factory, Graph SDK, MSAL

A controlled local live verification was performed after 10D implementation. It did not add OAuth, credentials, MSAL, or Graph SDK to ECI. See [Controlled Live Microsoft Graph Verification](#controlled-live-microsoft-graph-verification).

ADR-015 and credential-store ADRs remain deferred until a focused connector architecture review. Phase 10E did not create them.

## Controlled Live Microsoft Graph Verification

After Phase 10D implementation, focused review, commit, push, and green GitHub Actions CI, a separate controlled local live verification was performed against the real Microsoft Graph API on **2026-08-20**.

This is a verification checkpoint, not a new architecture decision. No ADR is recorded for it.

### Verification boundary

The live flow was:

```text
Microsoft interactive OAuth
        ↓
temporary in-memory access token
        ↓
Microsoft Graph REST v1.0
        ↓
MicrosoftGraphCommunicationConnector
        ↓
CommunicationMessage
        STOP
```

The live verification intentionally stopped at the connector/domain boundary. It did not continue into `CommunicationIngestionService`, `CommunicationAnalysisWorkflowService`, `MockAIProvider`, Microsoft Foundry, Amazon Bedrock, PostgreSQL, analysis persistence, or connector-account persistence.

The wider workflow remains covered by mocked/offline integration tests.

### Microsoft identity setup

Non-secret architectural facts only:

- A dedicated personal Outlook.com test mailbox was used.
- A dedicated Entra app registration was created specifically for this verification.
- App name: `ECI Graph Live Verification`.
- Supported account type: Personal Microsoft accounts only.
- Platform: Mobile and desktop applications.
- Redirect URI: `http://localhost`.
- Public-client flow was configured.
- No client secret was created.
- Configured Microsoft Graph API permission: delegated `Mail.Read` only.
- Explicit `User.Read` was not configured as a Graph API permission; it had been removed from the app registration.
- No `Mail.ReadWrite`.
- No `Mail.Send`.
- No application `Mail.Read`.
- No admin-consent grant was used for this controlled test.
- Existing Phase 8 ECI Entra applications were not reused.

`Mail.Read` was used because message-body access is required. `Mail.ReadBasic` remains insufficient for body-based analysis.

This successful verification used a personal Microsoft account test scenario. It does not prove that admin consent is universally unnecessary, that all Microsoft tenants permit user consent, or that production consent architecture is complete.

No Microsoft account email address, Application (client) ID, Object ID, tenant ID, access token, refresh token, authorization code, browser callback query, or consent-session identifier is recorded here.

### Existing ECI Entra identities

The live Graph verification did not reuse:

- `eci-api-auth-dev`
- `eci-auth-verifier-dev`
- `eci-github-deploy-dev`
- Azure managed identities

Mailbox OAuth is a different trust and use case from ECI API authentication, deployment identity, and runtime managed identity. The dedicated Graph app registration therefore remained separate.

`ECI Graph Live Verification` is a controlled development-verification identity. It is not a production app registration, not the final customer OAuth app, and not an enterprise multi-tenant OAuth architecture. Production identity design remains deferred.

### Temporary local workspace

A temporary local workspace outside the ECI repository was used. Conceptually it contained:

- an isolated Python virtual environment
- MSAL installed only in that temporary environment
- a temporary verification script

Those files are not part of the ECI repository and were not added by this checkpoint. MSAL was not added to `pyproject.toml` or `requirements.txt`.

### Authentication behavior

The temporary script used MSAL Python `PublicClientApplication.acquire_token_interactive(...)` for browser-based public-client authentication.

The scope requested by the script was `https://graph.microsoft.com/Mail.Read`.

The live script held the resulting access token in memory only and supplied it through `AccessTokenProvider`. No refresh token, token cache, or credential file was added to ECI.

This checkpoint does not claim production refresh-token management, token-cache architecture, credential resolver, secret-manager integration, production OAuth lifecycle, or a production callback API.

### Consent screen

Microsoft's consent UI displayed the expected delegated mail-read permission plus standard delegated-authentication identity/continued-access consent.

Bounded facts only:

- The only configured Microsoft Graph API permission was delegated `Mail.Read`.
- The consent UI also showed standard identity/basic-profile sign-in access. That is treated as ordinary OpenID/OAuth interactive sign-in consent, not as a separately configured ECI Graph API permission such as `User.Read`.
- The consent UI also showed continued-access wording. That is treated as Microsoft's standard delegated OAuth behavior, not as ECI implementing `offline_access`, refresh-token persistence, or a token cache.

Mailbox address, screenshots, callback URL, authorization URL, and token details are not recorded.

### Live test design

The verification used the real committed `MicrosoftGraphCommunicationConnector` with:

- a real `httpx.Client`
- a temporary in-memory access-token callable
- `ConnectorMessageQuery(limit=1)`

The connector then performed the real Graph read path. The test intentionally requested only one message. Expected network pattern:

1. 1 × `GET /v1.0/me/messages`
2. 1 × `GET /v1.0/me/messages/{id}`

No attachments call. No MIME `$value`. No second page. No profile lookup. No send. No modify. No delete. No Graph SDK call. No AI call. No database call.

### Synthetic mailbox test

One dedicated Outlook.com test mailbox was used. One synthetic test message with no meaningful personal or business data was placed in the mailbox. Live verification intentionally requested only one message. No message content was printed by the verification script.

Email address, sender, recipient, subject, message body, message ID, conversation ID, categories, and timestamps are not recorded here.

### Successful verification result

Validated outcomes:

- Microsoft interactive OAuth succeeded
- delegated `Mail.Read` consent succeeded
- real Microsoft Graph authentication succeeded
- real `/me/messages` list succeeded
- real `/me/messages/{id}` fetch succeeded
- `MicrosoftGraphCommunicationConnector` successfully normalized the Graph response
- exactly one `CommunicationMessage` was produced
- connector `provider == "microsoft_graph"`
- normalized `source_type == SourceType.EMAIL`
- normalized body was non-empty
- message content was not printed

Terminal result:

```text
Live Microsoft Graph connector verification: PASS
```

No credentials or mailbox content are recorded here.

### What this proves

Phase 10D has now been validated at two levels.

**Automated/offline verification.** `MockTransport`-based tests prove Graph request construction, `$top` / `$select`, one-page list semantics, sequential fetch, `@odata.nextLink` opacity, nextLink origin/path validation before bearer-token use, unsafe continuation URL rejection, redirect protection, message-id quoting, text-body normalization, HTML fallback, sender/from fallback, recipients, subject, timestamps, categories/labels, `bodyPreview` non-fallback, attachment exclusion, error mapping, token/content privacy, and ingestion-boundary interoperability. Those attack and error paths were not live-tested.

**Controlled live verification.** Real Microsoft Graph verification proves:

- the dedicated public-client OAuth setup can obtain delegated `Mail.Read` access
- the token can be supplied through the adapter's existing in-memory token interface
- the real `/me/messages` endpoint is compatible with the committed adapter
- the real message fetch endpoint is compatible with the committed adapter
- a real Graph message response can be normalized into the existing ECI `CommunicationMessage` model
- `SourceType.EMAIL` is produced
- normalized body is non-empty

The live Graph verification exercised only the successful path. Mocked edge-case coverage is not attributed to this live test.

### What is not proven

The controlled live test does not prove or implement:

- production Microsoft OAuth lifecycle
- production redirect/callback API routes
- persistent token cache
- refresh-token lifecycle inside ECI
- credential resolver integration
- connector-account → `credential_ref` → credential resolver composition
- production secret-manager integration
- multi-user Microsoft Graph mailbox onboarding
- work/school Microsoft 365 tenant onboarding
- admin-consent workflows
- shared mailboxes
- application `Mail.Read`
- client-credentials flow
- tenant-wide mailbox access
- background synchronization
- Graph delta query
- webhook/subscription handling
- mailbox change notifications
- attachments
- MIME `$value`
- send
- modify
- delete
- multi-page live pagination
- live nextLink continuation
- live `401`/`403`/`404`/`429`/`5xx` behavior
- live rate-limit behavior
- large-mailbox behavior
- large-message behavior
- AI analysis of live Graph content, including Microsoft Foundry, Amazon Bedrock, and `MockAIProvider`
- persistence of live Graph-derived analysis
- Azure-hosted OAuth
- AWS-hosted OAuth
- production Graph OAuth architecture

### Privacy and data minimization

- Real Graph JSON existed only transiently during request handling.
- The live verification did not persist the fetched Graph message. The designed workflow may persist derived analysis later; that path was not exercised live.
- No live Graph message content was sent to Microsoft Foundry, Amazon Bedrock, or `MockAIProvider`. The live test stopped before analysis.
- No live Graph content was written to PostgreSQL.
- No live Graph content was intentionally logged.
- No access token was intentionally logged.
- Verification output contained bounded status information only.
- The test mailbox contained only synthetic verification content relevant to this test.

These statements describe the verification procedure and the adapter's existing bounded logging. They are not stronger guarantees than the implementation supports.

### Connector-account boundary

Live verification did not exercise `connector_accounts`, `credential_ref`, `ConnectorAccountService`, a credential resolver, or database-backed mailbox selection.

The live token was supplied directly through `AccessTokenProvider`. That remains intentionally separate from Phase 10B persistence.

Future production composition remains conceptually:

```text
authenticated ECI user
        ↓
owned connector account
        ↓
credential_ref
        ↓
credential resolver
        ↓
token provider
        ↓
MicrosoftGraphCommunicationConnector
```

That composition is not implemented in this checkpoint.

### Implementation CI checkpoint

Phase 10D implementation commit:

- `74c2a82` — `feat: add Microsoft Graph read-only connector`
- GitHub Actions run `32372699620`
- Result: PASS

CI proves the mocked/offline committed code and tests. The controlled local live Microsoft Graph verification was a separate local execution. The live Graph call did not run in GitHub Actions.

## Phase 10E Finalization

Phase 10E closed Phase 10 with documentation alignment and offline regression only.

It:

- introduced no application code
- introduced no new runtime dependencies
- introduced no new tests
- performed an architecture consistency review against the committed 10A–10D code
- aligned shared architecture, API, diagram, cloud, and root README documentation
- reran complete offline regression
- formally closed Phase 10

No new runtime capability was introduced. Controlled Gmail and Graph live-verification records from 10C and 10D remain the authoritative live-check documentation; they are not repeated here.

### Authoritative implemented architecture

```text
CommunicationConnector
        ↑
vendor adapter
(fake / Gmail / Microsoft Graph)
        ↓
CommunicationMessage
        ↓
CommunicationIngestionService
        ↓
CommunicationAnalysisWorkflowService
        ↓
CommunicationAnalysisService
        ↓
AIProvider
```

Key boundaries after Phase 10:

- Domain owns the `CommunicationConnector` contract.
- Application depends on the connector interface, not vendor types.
- Gmail and Microsoft Graph adapters live in infrastructure.
- Both normalize email to `SourceType.EMAIL`.
- Provider identity remains separate (`gmail`, `microsoft_graph`).
- `AIProvider` is unchanged.
- Connector adapters do not persist raw mail, call `AIProvider`, own OAuth, resolve connector accounts, or expose HTTP routes.

There is no connector factory in the repository. The API does not import concrete connectors.

### Phase 10 closure

Phase 10 now proves:

```text
External communication provider
        ↓
vendor-neutral CommunicationConnector
        ↓
normalized CommunicationMessage
        ↓
existing ECI analysis workflow boundary
```

plus:

- user-owned connector account persistence
- opaque credential references
- Gmail REST v1 read-only adapter
- Microsoft Graph REST v1.0 read-only adapter
- provider-neutral domain contract
- controlled local live adapter compatibility checks (stop at `CommunicationMessage`)
- security and privacy boundaries
- full automated offline regression

This does not make ECI a complete production email product.

### Deferred production capabilities

The following remain deliberately deferred product/production capabilities, not defects:

- production Gmail OAuth lifecycle
- production Microsoft OAuth lifecycle
- persistent refresh-token handling
- secret manager integration
- credential resolver implementation
- `connector_account` → `credential_ref` → live token composition
- user-facing connector API routes
- production mailbox onboarding
- multi-user provider onboarding
- work/school Microsoft 365 onboarding
- Google restricted-scope production verification/compliance
- background synchronization
- Gmail History API
- Microsoft Graph delta query
- sync-state persistence
- webhooks/subscriptions
- push notifications
- attachments
- raw-message persistence
- sending
- replying
- `Mail.Send`
- `Mail.ReadWrite`
- `gmail.send`
- `gmail.modify`
- automatic replies
- generated-reply execution
- cloud-hosted mailbox OAuth
- live mailbox → AI provider verification
- live mailbox → PostgreSQL analysis persistence verification

Future conceptual credential composition remains unimplemented:

```text
authenticated ECI user
        ↓
owned connector account
        ↓
credential_ref
        ↓
credential resolver
        ↓
AccessTokenProvider
        ↓
provider connector
```

`connector_accounts.credential_ref` and adapter `AccessTokenProvider` exist. A credential resolver that joins them does not.

ADR-015 and credential-store ADRs remain deferred. Phase 10E did not lock down secret store, resolver, OAuth lifecycle, Gmail History vs Graph delta, connector API surface, or sync architecture.

### Phase 11 boundary

Next roadmap phase: **Phase 11 — Workflow Automation**.

Likely future workflow capabilities include generated-reply approval, action execution, and send/reply workflows. Phase 11 is not required to absorb every remaining connector-production topic. Credential resolver, provider OAuth, synchronization, connector APIs, and production mailbox onboarding may be Phase 11+ or later focused phases.

### Local final regression

Recorded after Phase 10E documentation edits. Local only. Not a GitHub Actions run.

| Check | Result |
|---|---|
| `python -m pip check` | No broken requirements found |
| `python -m ruff check .` | All checks passed |
| `python -m pytest` | 697 passed, 47 skipped |
| `git diff --check` | passed (no whitespace errors) |

Local final regression passed.

CI: pending commit/push.
