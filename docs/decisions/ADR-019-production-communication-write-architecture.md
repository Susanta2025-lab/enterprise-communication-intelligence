# ADR-019: Production Communication Write Architecture

## Status

Accepted

The decision is implemented for Phase 12C. `MicrosoftGraphCommunicationActionExecutor` is a provider-specific write adapter behind `CommunicationActionExecutor`. It is not injected into `WorkflowActionExecutionService`. There is no HTTP execute route, no Gmail writer, and no `communications:send` permission.

## Date

Phase 12 (Production Communication Execution)

## Context

Phase 11D introduced a vendor-neutral write port and a deterministic fake. Phase 12A snapshotted mailbox execution-target provenance onto `WorkflowAction`. Phase 12B added `CommunicationCredentialResolver`, which turns `ConnectorAccount.credential_ref` into an on-demand `AccessTokenProvider`.

The first real communication write must not collapse those boundaries. Adding `reply()` to `MicrosoftGraphCommunicationConnector` would mix read and write authorization, error models, and tests. Putting `credential_ref` or a raw token on `CommunicationActionExecution` would reverse Phase 12B. Resolving credentials inside `WorkflowActionExecutionService` after TX1, or looking up a connector account without owner scope, would weaken Phase 12A ownership and the pre-side-effect readiness model.

Microsoft Graph already exposes a native reply operation that derives recipients and conversation semantics from the original message. A workflow `REPLY` therefore needs only the approved snapshot and the Graph message resource id.

A retry of `/reply` can duplicate email. Graph `202 Accepted` has no reply resource body, so this slice cannot persist a provider result identifier. Some HTTP and transport failures leave the side-effect outcome uncertain; coercing those into durable `FAILED` would encourage unsafe resend.

## Decision

Keep read and write ports separate. Implement the first production writer as a Microsoft Graph infrastructure adapter that consumes an injected HTTP client and `AccessTokenProvider`.

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

- `CommunicationConnector` remains read-only. `MicrosoftGraphCommunicationConnector` does not gain `reply()` or `send()`.
- `CommunicationActionExecutor` remains the write boundary. Provider-specific writers live in `app/infrastructure/executors/`.
- `MicrosoftGraphCommunicationActionExecutor` receives `httpx.Client` and `AccessTokenProvider`. It does not read the environment, look up `credential_ref`, load `ConnectorAccount`, or implement OAuth.
- `CommunicationActionExecution` is unchanged: `action_id`, `action_type`, `approved_reply_body`, `connector_account_id`, `provider_message_id`, `provider`. It does not carry `credential_ref`, tokens, scopes, or `owner_user_id`.
- Graph `WorkflowActionType.REPLY` uses native `POST /me/messages/{id}/reply`. It does not use `sendMail`, `createReply`, draft-then-send, or `replyAll`.
- The Graph `comment` is exactly `approved_reply_body`. The adapter does not add a greeting, signature, quoted original, subject, or recipients. Graph determines reply addressing from the original message.
- `provider_message_id` is the Graph `message.id` and is URL-encoded with `quote(..., safe="")` before it is placed in the path.
- The access token is obtained when `execute` runs, not at import or process startup.
- Token lookup failure, a blank returned token, and credential-resolver errors raise `ServiceUnavailableError`. They are not converted into `CommunicationActionExecutionError` because no Graph request has occurred.
- HTTP `202` is success. Success does not parse or persist a response body. `execute` continues to return `None`.
- Definite provider rejection raises `CommunicationActionExecutionError`: ordinary 4xx except `408`, plus 3xx responses that are not followed. Graph `429` is a definite refusal of that request (throttled before accept); the adapter does not retry, sleep on `Retry-After`, or resend. Graph `409` is treated as a definite conflict rejection of that request, not an uncertain completion.
- Transport failure, timeout, Graph `408`, Graph 5xx, and unexpected non-202 2xx responses raise `ServiceUnavailableError`. They are not coerced into a definite `FAILED` signal. Phase 12F will finalize uncertain-outcome reconciliation. This slice does not introduce `EXECUTION_UNKNOWN`, retry, or an outbox.
- Redirects are not followed. Each Graph POST sets `follow_redirects=False` so an injected client cannot forward `Authorization` to another host.
- The adapter does not retry timeout, 429, 5xx, or connection errors. Graph `/reply` is not treated as idempotent.
- There is no HTTP execute route and no `communications:send` permission in this slice.
- Production multi-provider routing is deferred. No safe provider-routing composition is introduced in 12C. A later execute-integration slice may compose account-driven routing through a scoped execution context or factory without putting `credential_ref`, tokens, or `owner_user_id` on `CommunicationActionExecution`. A global `ACTION_EXECUTOR` switch is still rejected because it cannot represent users with multiple provider accounts. Unit tests compose `EnvironmentCommunicationCredentialResolver` → `AccessTokenProvider` → the Graph executor with `httpx.MockTransport`. Workflow tests continue to use `FakeCommunicationActionExecutor`.

## Alternatives Considered

- **Add `reply()` / `send()` to `MicrosoftGraphCommunicationConnector`** — rejected. Fetch and write have different scopes, error models, and tests. The read adapter stays read-only.
- **Use `POST /me/sendMail` for `WorkflowActionType.REPLY`** — rejected. That models a new message. Native `/reply` preserves Graph conversation semantics.
- **Use `createReply` then send a draft** — rejected. Extra state and requests are unnecessary for an immutable approved snapshot.
- **Put `credential_ref` or a raw token on `CommunicationActionExecution`** — rejected. Phase 12B exists specifically to keep locators and tokens off the command.
- **Resolve credentials inside `WorkflowActionExecutionService`** — rejected. The application service remains unaware of tokens. Readiness stays a composition concern.
- **Look up `ConnectorAccount` without owner scope to obtain `credential_ref`** — rejected. Phase 12A owner-scoped account access is not bypassed.
- **Add `owner_user_id` to the execution command to make routing easier** — rejected. Widening the command is an architectural change, not a 12C shortcut.
- **Introduce `RoutedCommunicationActionExecutor` or `ACTION_EXECUTOR=microsoft_graph` in 12C** — rejected for this slice. No routing composition is implemented here. A global switch cannot represent users with multiple provider accounts. A later scoped factory or execution context remains possible without widening the execution command.
- **Treat every Graph 4xx as definite `FAILED`, including 408** — rejected. 408 can leave the side-effect outcome uncertain.
- **Map timeout, transport failure, or 5xx to `CommunicationActionExecutionError`** — rejected. That would persist `FAILED` and encourage unsafe resend.
- **Map credential unavailability or a blank token to `CommunicationActionExecutionError`** — rejected. No Graph request has occurred, so that would be a false definite send failure.
- **Add `EXECUTION_UNKNOWN`, retry, or an outbox in 12C** — rejected. Phase 12F owns uncertain-outcome documentation and reconciliation.
- **Add Microsoft Graph SDK, MSAL, or Azure Identity mailbox credentials** — rejected. The writer uses `httpx` REST like the read adapter. Mailbox OAuth remains external configuration.

## Consequences

- A production-capable Graph reply adapter exists and is proven offline. It is not reachable from REST and is not the default `WorkflowActionExecutionService` executor.
- Future composition remains:

```text
ConnectorAccount.credential_ref
        ↓
CommunicationCredentialResolver
        ↓
AccessTokenProvider
        ↓
MicrosoftGraphCommunicationActionExecutor
```

- Fake execution stays credential-independent. Standard workflow tests do not instantiate the Graph writer.
- Graph `/reply` requires delegated `Mail.Send` against the real service. That consent is documentation-only in 12C. Existing `Mail.Read` read-side assumptions are unchanged. `Mail.ReadWrite` is not required.
- If the adapter is later wired into workflow execution, `CommunicationActionExecutionError` remains the definite `FAILED` path. Uncertain failures remain `ServiceUnavailableError` so stored status can stay `EXECUTING` until Phase 12F.

## Benefits

- Read and write stay on separate ports with separate tests.
- Approved-snapshot authority is preserved through the first real send path.
- Credential locators and tokens stay out of workflow persistence and the execution command.
- Conservative failure mapping avoids turning an unknown send outcome into durable `FAILED`.

## Trade-offs

- Production workflow routing is not implemented in 12C. Operators cannot send a Graph reply through the current application composition or HTTP API.
- There is no live Graph send validation in normal pytest.
- Graph `/reply` returns no resource body, so no provider result identifier is stored.
- Uncertain external side effects are not yet reconciled. The workflow status model is unchanged.

## Related Components

- `app/infrastructure/executors/microsoft_graph.py`
- `app/domain/interfaces/communication_action_executor.py`
- `app/domain/interfaces/communication_credential_resolver.py`
- `app/infrastructure/credentials/environment.py`
- `app/infrastructure/connectors/microsoft_graph/connector.py`
- [ADR-017](ADR-017-communication-action-execution-boundary.md)
- [ADR-018](ADR-018-workflow-execution-target-provenance.md)
- [Phase 12](../roadmap/phase-12-production-communication-execution.md)
