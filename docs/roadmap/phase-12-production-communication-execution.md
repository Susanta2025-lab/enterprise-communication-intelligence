# Phase 12 — Production Communication Execution

## Objective

Enable **user-approved real communication execution** for mailbox replies.

Phase 12 is not automatic replies. Automatic send/reply remains deferred to Phase 13+.

```text
Phase 12
= user-approved real communication execution

automatic replies
= deferred to Phase 13+
```

The Phase 11 execution model is preserved:

```text
WorkflowActionExecutionService
CommunicationActionExecution
CommunicationActionExecutor
FakeCommunicationActionExecutor
```

and the two-transaction boundary:

```text
TX1 APPROVED → EXECUTING (commit, close UoW)
executor (no DB/UoW)
TX2 EXECUTING → EXECUTED | FAILED
```

## Status

Phase 12 is **In Progress**.

- **12A is Completed:** analysis `connector_account_id` provenance, workflow execution-target snapshot (`connector_account_id` + `provider_message_id`), owned `ACTIVE` ConnectorAccount validation before `APPROVED` → `EXECUTING`, expanded frozen execution command, Alembic `12a0001`, ADR-018. Fake execution only.
- **12B is Completed:** provider-neutral `CommunicationCredentialResolver`, environment-backed local/dev resolver, shared `AccessTokenProvider` contract, write-scope readiness documentation. Environment-backed local/dev lookup only. Fake execution remains credential-independent.
- **12C is Completed:** Microsoft Graph reply adapter implemented as `MicrosoftGraphCommunicationActionExecutor`. Production workflow routing/composition is deferred to the provider-routing/execute integration slice. The adapter is not reachable from the REST API. ADR-019.
- **12D is Completed:** Gmail reply adapter implemented as `GmailCommunicationActionExecutor`. Production workflow routing/composition remains deferred. The adapter is not reachable from the REST API. ADR-019 extended.
- **12E is Not started:** Execute API and `communications:send`.
- **12F is Not started:** Failure semantics, privacy, documentation, and regression.

Phase 11 remains **Completed**.

## Planned slices

### 12A — Execution Target, Routing & Executability Foundation

Establish which mailbox account and which original provider message an approved `WorkflowAction` will later execute against.

```text
mailbox connector ingestion
        ↓
CommunicationMessage
        ↓
analysis persistence
  connector_account_id
  provider message_id
        ↓
explicit WorkflowAction creation
        ↓
snapshot execution target
  connector_account_id
  provider_message_id
        ↓
PENDING → APPROVED
        ↓
execution service validates target
        ↓
owned active ConnectorAccount
        ↓
FakeCommunicationActionExecutor
```

12A still performs **fake execution only**. It does not send mail.

### 12B — Credential Resolution + Write-Scope Readiness

Establish the provider-neutral credential-resolution boundary required by later Gmail and Microsoft Graph write executors.

```text
ConnectorAccount.credential_ref
        ↓
CommunicationCredentialResolver.resolve(credential_ref, provider)
        ↓
AccessTokenProvider
        ↓
access token (on demand)
```

Implemented in this slice:

- Domain port `CommunicationCredentialResolver` in `app/domain/interfaces/communication_credential_resolver.py`
- Shared `AccessTokenProvider = Callable[[], str]` extracted to that domain module and re-exported from `app/infrastructure/connectors/common/auth.py`
- Infrastructure `EnvironmentCommunicationCredentialResolver` in `app/infrastructure/credentials/environment.py`
- Provider-neutral errors `CommunicationCredentialUnavailableError` and `UnsupportedCommunicationCredentialProviderError`

`credential_ref` remains an opaque locator stored only on `ConnectorAccount`. It is not an access token. Tokens are not persisted, not copied onto `WorkflowAction` or `CommunicationActionExecution`, and not exposed through HTTP.

Environment mapping (local/development only):

```text
provider = gmail, credential_ref = demo-account
→ ECI_COMMUNICATION_CREDENTIAL_GMAIL_DEMO_ACCOUNT_ACCESS_TOKEN

provider = microsoft_graph, credential_ref = demo-account
→ ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_DEMO_ACCOUNT_ACCESS_TOKEN
```

Locator normalization is strict (`^[A-Za-z][A-Za-z0-9-]{0,62}$`). Hyphens become underscores and the name is uppercased. Underscores are rejected so `a-b` and `a_b` cannot select the same secret. Unsafe characters cannot produce an environment lookup. Provider (`gmail` / `microsoft_graph`) is required and is part of the environment variable name because `credential_ref` is not uniquely constrained on `ConnectorAccount`. `fake` is rejected because fake execution does not resolve credentials.

Lookup timing: `resolve()` validates locator and provider, then returns a callable. The callable reads the environment on each invocation. There is no global token cache. Missing mailbox environment variables do not prevent application startup or ordinary tests.

This slice is **credential resolution only**. It does not send email.

Not implemented in 12B:

- production OAuth authorization-code flow, PKCE, consent, or refresh
- Azure Key Vault / AWS Secrets Manager mailbox secret lookup
- `RoutedCommunicationActionExecutor`
- Gmail or Microsoft Graph write executors
- HTTP execute route or `communications:send`
- injecting the resolver into `WorkflowActionExecutionService`

`WorkflowActionExecutionService` remains unaware of tokens. Fake execution still succeeds for `ACTIVE` accounts with `credential_ref=None` because the fake executor does not resolve credentials. Real provider execution will require resolution later.

Future write-scope readiness (documented only; not requested programmatically; not enabled now):

- Gmail current read: `https://www.googleapis.com/auth/gmail.readonly`
- Gmail future reply: also `https://www.googleapis.com/auth/gmail.send` (not enabled; planned executor retrieves original-message metadata before constructing the reply, so `gmail.readonly` is retained)
- Microsoft Graph current read: delegated `Mail.Read`
- Microsoft Graph future reply: delegated `Mail.Send` (not enabled; `Mail.ReadWrite` is not required for the planned `/reply` operation)

Google OAuth app configuration and Entra delegated-scope consent are not changed in 12B.

Credential resolution boundary implemented ≠ production OAuth implemented.

### 12C — Microsoft Graph Reply Executor

```text
12C
= Microsoft Graph reply adapter implemented

production workflow routing/composition
= deferred to the provider-routing/execute integration slice
```

Implemented in this slice:

- Infrastructure `MicrosoftGraphCommunicationActionExecutor` in `app/infrastructure/executors/microsoft_graph.py`
- Native Graph `POST /v1.0/me/messages/{id}/reply` with `{"comment": approved_reply_body}`
- Injected `httpx.Client` and `AccessTokenProvider`; token lookup happens at execute time
- Conservative failure mapping: definite Graph rejection → `CommunicationActionExecutionError`; timeout/transport/5xx/408/credential-unavailable/blank-token → `ServiceUnavailableError`
- ADR-019 production write architecture
- Offline `httpx.MockTransport` coverage, including environment-resolver → token provider → Graph executor composition

Not implemented in 12C:

- injection into `WorkflowActionExecutionService`
- `RoutedCommunicationActionExecutor`
- HTTP execute route or `communications:send`
- Gmail writer
- live Graph send tests
- retry, `EXECUTION_UNKNOWN`, outbox, or reconciliation

`CommunicationConnector` remains read-only. Fake execution remains the workflow test path.

### 12D — Gmail Reply Executor

```text
12D
= Gmail reply adapter implemented

production workflow routing/composition
= deferred to the provider-routing/execute integration slice
```

Implemented in this slice:

- Infrastructure `GmailCommunicationActionExecutor` in `app/infrastructure/executors/gmail.py`
- Metadata GET `format=metadata`, RFC 2822 reply construction, then `POST /gmail/v1/users/me/messages/send` with `raw` + `threadId`
- Injected `httpx.Client`, `AccessTokenProvider`, and trusted `mailbox_address`; token lookup happens at execute time
- Ordinary `REPLY` only: `Reply-To` else `From`; original subject preserved; no reply-all, drafts, or attachments
- Conservative failure mapping aligned with 12C: definite provider rejection → `CommunicationActionExecutionError`; timeout/transport/5xx/408/credential-unavailable/blank-token → `ServiceUnavailableError`
- ADR-019 extended for Gmail threading/send
- Offline `httpx.MockTransport` coverage, including environment-resolver → token provider → Gmail executor composition

Not implemented in 12D:

- injection into `WorkflowActionExecutionService`
- `RoutedCommunicationActionExecutor`
- HTTP execute route or `communications:send`
- live Gmail send tests
- retry, `EXECUTION_UNKNOWN`, outbox, or reconciliation

`CommunicationConnector` remains read-only. Fake execution remains the workflow test path.

### 12E — Execute API + communications:send

`POST /api/v1/workflow-actions/{id}/execute` and the send permission. Not implemented in this slice.

### 12F — Failure Semantics, Privacy, Documentation & Regression

Provider-result persistence, uncertain-outcome documentation, and Phase 12 closure. Not implemented in this slice.

## Deliverables

- [x] Phase 12A — Execution Target, Routing & Executability Foundation (completed)
- [x] Phase 12B — Credential Resolution + Write-Scope Readiness (completed)
- [x] Phase 12C — Microsoft Graph Reply Executor (completed)
- [x] Phase 12D — Gmail Reply Executor (completed)
- [ ] Phase 12E — Execute API + communications:send
- [ ] Phase 12F — Failure Semantics, Privacy, Documentation & Regression

## Unavailable until later Phase 12 slices

- production OAuth, token refresh, Azure Key Vault, AWS Secrets Manager
- production workflow routing of the Graph or Gmail reply adapters
- Graph `sendMail`
- HTTP execute route
- `communications:send`
- retry, `EXECUTION_UNKNOWN`, outbox, workers
- automatic replies
