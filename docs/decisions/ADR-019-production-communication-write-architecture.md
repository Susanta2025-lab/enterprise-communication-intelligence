# ADR-019: Production Communication Write Architecture

## Status

Accepted

The decision is implemented for Phase 12C and extended in Phase 12D and Phase 12E. `MicrosoftGraphCommunicationActionExecutor` and `GmailCommunicationActionExecutor` are provider-specific write adapters behind `CommunicationActionExecutor`. Phase 12E routes them through `CommunicationActionExecutorFactory` from an owned `ConnectorAccount` and exposes `POST /api/v1/workflow-actions/{action_id}/execute` protected by `communications:send`. Credential lookup remains the environment-backed local/dev resolver. Retry, `EXECUTION_UNKNOWN`, and outbox work remain deferred to Phase 12F.

## Date

Phase 12 (Production Communication Execution)

## Context

Phase 11D introduced a vendor-neutral write port and a deterministic fake. Phase 12A snapshotted mailbox execution-target provenance onto `WorkflowAction`. Phase 12B added `CommunicationCredentialResolver`, which turns `ConnectorAccount.credential_ref` into an on-demand `AccessTokenProvider`.

The first real communication write must not collapse those boundaries. Adding `reply()` to `MicrosoftGraphCommunicationConnector` would mix read and write authorization, error models, and tests. Putting `credential_ref` or a raw token on `CommunicationActionExecution` would reverse Phase 12B. Resolving credentials inside `WorkflowActionExecutionService` after TX1, or looking up a connector account without owner scope, would weaken Phase 12A ownership and the pre-side-effect readiness model.

Microsoft Graph already exposes a native reply operation that derives recipients and conversation semantics from the original message. A workflow `REPLY` therefore needs only the approved snapshot and the Graph message resource id.

A retry of `/reply` can duplicate email. Graph `202 Accepted` has no reply resource body, so this slice cannot persist a provider result identifier. Some HTTP and transport failures leave the side-effect outcome uncertain; coercing those into durable `FAILED` would encourage unsafe resend.

Gmail has no native reply operation equivalent to Graph `/reply`. A Gmail `REPLY` therefore fetches original-message metadata, constructs an RFC 2822 plain-text reply, base64URL-encodes the entire MIME message, and posts `users.messages.send` with the original `threadId`. Gmail send is not treated as idempotent.

## Decision

Keep read and write ports separate. Implement production writers as provider-specific infrastructure adapters that consume an injected HTTP client and `AccessTokenProvider`. Graph uses a native reply operation. Gmail uses metadata fetch plus RFC 2822 construction plus `messages.send`.

```text
CommunicationActionExecution
        ↓
MicrosoftGraphCommunicationActionExecutor
        ↓
AccessTokenProvider()
        ↓
POST https://graph.microsoft.com/v1.0/me/messages/{provider_message_id}/reply
        ↓
{"comment": approved_reply_body}
        ↓
202 Accepted
```

```text
CommunicationActionExecution
        ↓
GmailCommunicationActionExecutor
        ↓
AccessTokenProvider()   (exactly once)
        ↓
GET https://gmail.googleapis.com/gmail/v1/users/me/profile
        ↓
validated emailAddress → RFC From
        ↓
GET https://gmail.googleapis.com/gmail/v1/users/me/messages/{provider_message_id}
    ?format=metadata
        ↓
RFC 2822 reply (From, To, Subject, In-Reply-To, References, text/plain body)
        ↓
POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send
        ↓
{"raw": base64url(RFC message), "threadId": original threadId}
        ↓
200
```

- `CommunicationConnector` remains read-only. `MicrosoftGraphCommunicationConnector` and `GmailCommunicationConnector` do not gain `reply()` or `send()`.
- `CommunicationActionExecutor` remains the write boundary. Provider-specific writers live in `app/infrastructure/executors/`.
- Each writer receives `httpx.Client` and `AccessTokenProvider`. Writers do not read the environment, look up `credential_ref`, load `ConnectorAccount`, or implement OAuth.
- Production routing uses an owned `ConnectorAccount` already loaded by `WorkflowActionExecutionService` through `connector_accounts.get_owned(...)`. `ProviderCommunicationActionExecutorFactory.create_for_account(account)` maps `gmail` and `microsoft_graph` accounts with a structurally valid `credential_ref` to the matching writer. It returns `None` for missing/blank/malformed locators, `fake`, and unknown providers. The factory does not query the database, call provider HTTP, or invoke the returned `AccessTokenProvider`. Token retrieval and provider I/O happen only after TX1 commits and the unit of work is closed.
- Gmail sender identity is discovered at execute time from `GET /gmail/v1/users/me/profile` → `emailAddress`, validated with the same single-mailbox rules used for reply recipients. `ConnectorAccount.external_account_id` remains an opaque provider-native identity and is not treated as a Gmail From address. No mailbox-address column is added. The profile address is not persisted, not added to `CommunicationActionExecution` or `WorkflowAction`, and not logged.
- `CommunicationActionExecution` is unchanged: `action_id`, `action_type`, `approved_reply_body`, `connector_account_id`, `provider_message_id`, `provider`. It does not carry `credential_ref`, tokens, scopes, `owner_user_id`, `mailbox_address`, or `external_account_id`.
- Graph `WorkflowActionType.REPLY` uses native `POST /me/messages/{id}/reply`. It does not use `sendMail`, `createReply`, draft-then-send, or `replyAll`.
- The Graph `comment` is exactly `approved_reply_body`. The adapter does not add a greeting, signature, quoted original, subject, or recipients. Graph determines reply addressing from the original message.
- `provider_message_id` is the Graph `message.id` or Gmail `message.id` and is URL-encoded with `quote(..., safe="")` before it is placed in a path.
- The access token is obtained when `execute` runs, not at import or process startup. One token is reused for the Gmail profile GET, metadata GET, and send POST.
- Token lookup failure, a blank returned token, and credential-resolver errors raise `ServiceUnavailableError`. They are not converted into `CommunicationActionExecutionError` because no provider send request has occurred.
- Graph HTTP `202` is success. Gmail send HTTP `200` is success. Success does not parse or persist a response body. `execute` continues to return `None`.
- Definite provider rejection raises `CommunicationActionExecutionError`: ordinary 4xx except `408`, plus 3xx responses that are not followed. Provider `429` is a definite refusal of that request; the adapter does not retry, sleep on `Retry-After`, or resend. Graph `409` is treated as a definite conflict rejection of that request, not an uncertain completion.
- Transport failure, timeout, provider `408`, provider 5xx, and unexpected non-success 2xx responses raise `ServiceUnavailableError`. They are not coerced into a definite `FAILED` signal. For Gmail, that mapping applies to the profile GET, metadata GET, and send POST. A profile or metadata failure never issues send. A malformed successful profile response (missing/invalid `emailAddress`) is `ServiceUnavailableError`. Phase 12F will finalize uncertain-outcome reconciliation. This slice does not introduce `EXECUTION_UNKNOWN`, retry, or an outbox.
- Redirects are not followed. Each provider request sets `follow_redirects=False` so an injected client cannot forward `Authorization` to another host.
- The adapters do not retry timeout, 429, 5xx, or connection errors. Graph `/reply` and Gmail `messages.send` are not treated as idempotent.
- Gmail threading requires the original `threadId`, the original `Subject` without automatic `Re:` prefixing, `In-Reply-To` set to the original RFC `Message-ID`, and `References` preserving any existing chain plus that `Message-ID` when it is not already the last identifier. A malformed `Message-ID` or `References` chain fails closed before send. The reply target is a valid `Reply-To` when present; otherwise `From`. A present but malformed, multi-recipient, or group `Reply-To` does not fall back to `From`. The action is ordinary `REPLY` only: recipients are not derived from `To`, `Cc`, or `Bcc`.
- The Gmail RFC `From` header is the authenticated profile `emailAddress`, not a value copied from the original message and not `external_account_id`. The Gmail metadata GET uses `format=metadata` and does not fetch the original body, attachments, or full MIME.
- `POST /api/v1/workflow-actions/{action_id}/execute` requires `communications:send` and a real principal (`AUTH_MODE=disabled` returns 401). Proposal/approval routes remain `communications:workflow`. The request has no body; the stored approved snapshot is authoritative.
- A global `ACTION_EXECUTOR` switch is rejected because it cannot represent users with multiple provider accounts. Factory routing is account-driven. Fake execution remains available for isolated tests and is not production-routed. `WorkflowActionNotExecutableError` maps to HTTP 409. Recorded definite `FAILED` is returned as HTTP 200 with status `FAILED`. Uncertain provider/credential failure after `EXECUTING` returns HTTP 503 and leaves the row `EXECUTING`.

## Alternatives Considered

- **Add `reply()` / `send()` to `MicrosoftGraphCommunicationConnector` or `GmailCommunicationConnector`** — rejected. Fetch and write have different scopes, error models, and tests. The read adapters stay read-only.
- **Use Gmail `drafts.create` then `drafts.send`** — rejected. Extra state is unnecessary for an immutable approved snapshot.
- **Copy original `To` / `Cc` / `Bcc` (reply-all)** — rejected. Phase 12D is ordinary `REPLY`.
- **Automatically prepend `Re:` to the Gmail subject** — rejected. Gmail thread association uses the original subject together with `threadId`, `In-Reply-To`, and `References`.
- **Use `POST /me/sendMail` for `WorkflowActionType.REPLY`** — rejected. That models a new message. Native `/reply` preserves Graph conversation semantics.
- **Use `createReply` then send a draft** — rejected. Extra state and requests are unnecessary for an immutable approved snapshot.
- **Put `credential_ref` or a raw token on `CommunicationActionExecution`** — rejected. Phase 12B exists specifically to keep locators and tokens off the command.
- **Resolve credentials inside `WorkflowActionExecutionService`** — rejected. The application service remains unaware of tokens. Readiness stays a composition concern.
- **Look up `ConnectorAccount` without owner scope to obtain `credential_ref`** — rejected. Phase 12A owner-scoped account access is not bypassed.
- **Add `owner_user_id` to the execution command to make routing easier** — rejected. Widening the command is an architectural change, not a 12C shortcut.
- **Introduce `RoutedCommunicationActionExecutor` or `ACTION_EXECUTOR=microsoft_graph`** — rejected. A global switch cannot represent users with multiple provider accounts. Account-driven `CommunicationActionExecutorFactory` is the routing seam.
- **Treat `external_account_id` as the Gmail From address or persist `mailbox_address`** — rejected. The identifier is opaque. Primary authenticated mailbox identity comes from `users/me/profile`. Aliases and reply-as are out of scope.
- **Inject `mailbox_address` on `CommunicationActionExecution` or the Gmail constructor for production composition** — rejected. Profile discovery uses the same token as metadata and send.
- **Treat every Graph 4xx as definite `FAILED`, including 408** — rejected. 408 can leave the side-effect outcome uncertain.
- **Map timeout, transport failure, or 5xx to `CommunicationActionExecutionError`** — rejected. That would persist `FAILED` and encourage unsafe resend.
- **Map credential unavailability or a blank token to `CommunicationActionExecutionError`** — rejected. No provider send request has occurred, so that would be a false definite send failure.
- **Add `EXECUTION_UNKNOWN`, retry, or an outbox in 12C or 12D** — rejected. Phase 12F owns uncertain-outcome documentation and reconciliation.
- **Add Microsoft Graph SDK, MSAL, Azure Identity, or a Google API SDK** — rejected. Writers use `httpx` REST like the read adapters. Mailbox OAuth remains external configuration.

## Consequences

- Production Graph and Gmail reply adapters are reachable through the execute API when the owned account is `ACTIVE`, the provider is `gmail` or `microsoft_graph`, and `credential_ref` is a structurally valid locator. The current secret backend is environment-backed local/dev lookup, not a managed secret store and not production OAuth.
- Composition is:

```text
owned ConnectorAccount
        ↓
CommunicationActionExecutorFactory
        ↓
credential_ref
        ↓
CommunicationCredentialResolver.resolve(...)
        ↓
AccessTokenProvider   (not invoked by the factory)
        ↓
MicrosoftGraphCommunicationActionExecutor
  or GmailCommunicationActionExecutor
```

- Fake execution stays credential-independent in isolated tests. The production execute API does not route `fake`.
- Graph `/reply` requires delegated `Mail.Send` against the real service. Gmail send requires `gmail.readonly` plus `gmail.send`. Those consents remain documentation-only.
- `CommunicationActionExecutionError` remains the definite `FAILED` path. Uncertain failures remain `ServiceUnavailableError` so stored status can stay `EXECUTING` until Phase 12F.

## Benefits

- Read and write stay on separate ports with separate tests.
- Approved-snapshot authority is preserved through the first real send path.
- Credential locators and tokens stay out of workflow persistence and the execution command.
- Conservative failure mapping avoids turning an unknown send outcome into durable `FAILED`.

## Trade-offs

- Production workflow routing exists for Graph and Gmail through the execute API. Operators still cannot rely on managed secret stores or OAuth refresh.
- There is no live Graph or Gmail send validation in normal pytest.
- Graph `/reply` returns no resource body. Gmail send returns a Message resource that is ignored. No provider result identifier is stored.
- Uncertain external side effects are not yet reconciled. The workflow status model is unchanged.

## Related Components

- `app/infrastructure/executors/factory.py`
- `app/domain/interfaces/communication_action_executor_factory.py`
- `app/application/services/workflow_action_execution.py`
- `app/infrastructure/executors/microsoft_graph.py`
- `app/infrastructure/executors/gmail.py`
- `app/domain/interfaces/communication_action_executor.py`
- `app/domain/interfaces/communication_credential_resolver.py`
- `app/infrastructure/credentials/environment.py`
- `app/infrastructure/connectors/microsoft_graph/connector.py`
- `app/infrastructure/connectors/gmail/connector.py`
- [ADR-017](ADR-017-communication-action-execution-boundary.md)
- [ADR-018](ADR-018-workflow-execution-target-provenance.md)
- [Phase 12](../roadmap/phase-12-production-communication-execution.md)
