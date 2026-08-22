# ADR-019: Production Communication Write Architecture

## Status

Accepted

The decision is implemented for Phase 12C and extended in Phase 12D. `MicrosoftGraphCommunicationActionExecutor` and `GmailCommunicationActionExecutor` are provider-specific write adapters behind `CommunicationActionExecutor`. Neither is injected into `WorkflowActionExecutionService`. There is no HTTP execute route and no `communications:send` permission. Production routing remains deferred.

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
AccessTokenProvider()
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
- Each writer receives `httpx.Client` and `AccessTokenProvider`. The Gmail writer also receives a trusted `mailbox_address` at composition time for the RFC `From` header. Writers do not read the environment, look up `credential_ref`, load `ConnectorAccount`, or implement OAuth. `mailbox_address` is not added to `CommunicationActionExecution`.
- `CommunicationActionExecution` is unchanged: `action_id`, `action_type`, `approved_reply_body`, `connector_account_id`, `provider_message_id`, `provider`. It does not carry `credential_ref`, tokens, scopes, or `owner_user_id`.
- Graph `WorkflowActionType.REPLY` uses native `POST /me/messages/{id}/reply`. It does not use `sendMail`, `createReply`, draft-then-send, or `replyAll`.
- The Graph `comment` is exactly `approved_reply_body`. The adapter does not add a greeting, signature, quoted original, subject, or recipients. Graph determines reply addressing from the original message.
- `provider_message_id` is the Graph `message.id` or Gmail `message.id` and is URL-encoded with `quote(..., safe="")` before it is placed in a path.
- The access token is obtained when `execute` runs, not at import or process startup. One token is reused for the Gmail metadata GET and send POST.
- Token lookup failure, a blank returned token, and credential-resolver errors raise `ServiceUnavailableError`. They are not converted into `CommunicationActionExecutionError` because no provider send request has occurred.
- Graph HTTP `202` is success. Gmail send HTTP `200` is success. Success does not parse or persist a response body. `execute` continues to return `None`.
- Definite provider rejection raises `CommunicationActionExecutionError`: ordinary 4xx except `408`, plus 3xx responses that are not followed. Provider `429` is a definite refusal of that request; the adapter does not retry, sleep on `Retry-After`, or resend. Graph `409` is treated as a definite conflict rejection of that request, not an uncertain completion.
- Transport failure, timeout, provider `408`, provider 5xx, and unexpected non-success 2xx responses raise `ServiceUnavailableError`. They are not coerced into a definite `FAILED` signal. For Gmail, that mapping applies to both the metadata GET and the send POST; a metadata failure never issues send. Phase 12F will finalize uncertain-outcome reconciliation. This slice does not introduce `EXECUTION_UNKNOWN`, retry, or an outbox.
- Redirects are not followed. Each provider request sets `follow_redirects=False` so an injected client cannot forward `Authorization` to another host.
- The adapters do not retry timeout, 429, 5xx, or connection errors. Graph `/reply` and Gmail `messages.send` are not treated as idempotent.
- Gmail threading requires the original `threadId`, the original `Subject` without automatic `Re:` prefixing, `In-Reply-To` set to the original RFC `Message-ID`, and `References` preserving any existing chain plus that `Message-ID` when it is not already the last identifier. A malformed `Message-ID` or `References` chain fails closed before send. The reply target is a valid `Reply-To` when present; otherwise `From`. A present but malformed, multi-recipient, or group `Reply-To` does not fall back to `From`. The action is ordinary `REPLY` only: recipients are not derived from `To`, `Cc`, or `Bcc`.
- The Gmail RFC `From` header is the trusted composed `mailbox_address`, not a value copied from the original message. The Gmail metadata GET uses `format=metadata` and does not fetch the original body, attachments, or full MIME.
- There is no HTTP execute route and no `communications:send` permission in this slice.
- Production multi-provider routing is deferred. No safe provider-routing composition is introduced in 12C or 12D. A later execute-integration slice may compose account-driven routing through a scoped execution context or factory without putting `credential_ref`, tokens, `owner_user_id`, `mailbox_address`, or `threadId` on `CommunicationActionExecution`. A global `ACTION_EXECUTOR` switch is still rejected because it cannot represent users with multiple provider accounts. Unit tests compose `EnvironmentCommunicationCredentialResolver` → `AccessTokenProvider` → the Graph or Gmail executor with `httpx.MockTransport`. Workflow tests continue to use `FakeCommunicationActionExecutor`.

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
- **Introduce `RoutedCommunicationActionExecutor` or `ACTION_EXECUTOR=microsoft_graph` in 12C** — rejected for this slice. No routing composition is implemented here. A global switch cannot represent users with multiple provider accounts. A later scoped factory or execution context remains possible without widening the execution command.
- **Treat every Graph 4xx as definite `FAILED`, including 408** — rejected. 408 can leave the side-effect outcome uncertain.
- **Map timeout, transport failure, or 5xx to `CommunicationActionExecutionError`** — rejected. That would persist `FAILED` and encourage unsafe resend.
- **Map credential unavailability or a blank token to `CommunicationActionExecutionError`** — rejected. No provider send request has occurred, so that would be a false definite send failure.
- **Add `EXECUTION_UNKNOWN`, retry, or an outbox in 12C or 12D** — rejected. Phase 12F owns uncertain-outcome documentation and reconciliation.
- **Add Microsoft Graph SDK, MSAL, Azure Identity, or a Google API SDK** — rejected. Writers use `httpx` REST like the read adapters. Mailbox OAuth remains external configuration.

## Consequences

- Production-capable Graph and Gmail reply adapters exist and are proven offline. They are not reachable from REST and are not the default `WorkflowActionExecutionService` executor.
- Future composition remains:

```text
owned ConnectorAccount
        ↓
credential_ref + trusted mailbox identity
        ↓
CommunicationCredentialResolver
        ↓
AccessTokenProvider
        ↓
MicrosoftGraphCommunicationActionExecutor
  or GmailCommunicationActionExecutor
```

- Fake execution stays credential-independent. Standard workflow tests do not instantiate the Graph or Gmail writer.
- Graph `/reply` requires delegated `Mail.Send` against the real service. Gmail send requires `gmail.readonly` plus `gmail.send`. Those consents remain documentation-only. Existing read-side assumptions are unchanged. `Mail.ReadWrite` is not required.
- If the adapter is later wired into workflow execution, `CommunicationActionExecutionError` remains the definite `FAILED` path. Uncertain failures remain `ServiceUnavailableError` so stored status can stay `EXECUTING` until Phase 12F.

## Benefits

- Read and write stay on separate ports with separate tests.
- Approved-snapshot authority is preserved through the first real send path.
- Credential locators and tokens stay out of workflow persistence and the execution command.
- Conservative failure mapping avoids turning an unknown send outcome into durable `FAILED`.

## Trade-offs

- Production workflow routing is not implemented in 12C or 12D. Operators cannot send a Graph or Gmail reply through the current application composition or HTTP API.
- There is no live Graph or Gmail send validation in normal pytest.
- Graph `/reply` returns no resource body. Gmail send returns a Message resource that is ignored. No provider result identifier is stored.
- Uncertain external side effects are not yet reconciled. The workflow status model is unchanged.

## Related Components

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
