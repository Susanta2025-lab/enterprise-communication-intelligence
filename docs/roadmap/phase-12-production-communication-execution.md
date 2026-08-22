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

Phase 12 is **Completed**.

- **12A is Completed:** analysis `connector_account_id` provenance, workflow execution-target snapshot (`connector_account_id` + `provider_message_id`), owned `ACTIVE` ConnectorAccount validation before `APPROVED` → `EXECUTING`, expanded frozen execution command, Alembic `12a0001`, ADR-018. Fake execution only in that slice; later slices routed production writers.
- **12B is Completed:** provider-neutral `CommunicationCredentialResolver`, environment-backed local/dev resolver, shared `AccessTokenProvider` contract, write-scope readiness documentation. Environment-backed local/dev lookup only. Fake execution remains credential-independent.
- **12C is Completed:** Microsoft Graph reply adapter implemented as `MicrosoftGraphCommunicationActionExecutor`. ADR-019. Routing and HTTP reachability were added later in 12E.
- **12D is Completed:** Gmail reply adapter implemented as `GmailCommunicationActionExecutor`. ADR-019 extended. That slice originally injected constructor `mailbox_address`; 12E replaced sender identity with `GET users/me/profile` → `emailAddress`. Routing and HTTP reachability were added later in 12E.
- **12E is Completed:** Execute API, `communications:send`, and account-driven production executor factory. Gmail sender identity from `users/me/profile`. ADR-019 extended for factory routing.
- **12F is Completed:** Failure semantics, privacy, documentation, and regression. ADR-020. `EXECUTION_UNKNOWN` is not implemented. Raw provider-result persistence is not added.

Phase 12 delivered **user-approved real communication execution**.

Phase 12 did not deliver automatic replies, production OAuth refresh, managed secret stores, retry/reconciliation, `EXECUTION_UNKNOWN`, exactly-once execution, or live-provider certification.

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
= deferred in this slice; completed later in 12E
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
= deferred in this slice; completed later in 12E
```

Implemented in this slice:

- Infrastructure `GmailCommunicationActionExecutor` in `app/infrastructure/executors/gmail.py`
- Metadata GET `format=metadata`, RFC 2822 reply construction, then `POST /gmail/v1/users/me/messages/send` with `raw` + `threadId`
- Injected `httpx.Client` and `AccessTokenProvider`; token lookup happens at execute time. This slice originally accepted constructor `mailbox_address`; current production composition discovers sender identity from `GET /gmail/v1/users/me/profile` (`emailAddress`) as of 12E.
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

```text
12E
= production routing + execute API + communications:send

retry / EXECUTION_UNKNOWN / outbox
= not implemented; documented in 12F / ADR-020
```

Implemented in this slice:

- `POST /api/v1/workflow-actions/{action_id}/execute` with no request body
- `communications:send` as a distinct capability from `communications:workflow`
- `CommunicationActionExecutorFactory` / `ProviderCommunicationActionExecutorFactory`
- `WorkflowActionExecutionService` selects a Graph or Gmail executor from the owned `ConnectorAccount` before `APPROVED` → `EXECUTING`
- Gmail sender identity from `GET /gmail/v1/users/me/profile` (`emailAddress`); constructor `mailbox_address` removed
- `WorkflowActionNotExecutableError` → HTTP 409
- Environment-backed credential lookup remains the local/dev secret backend

Not implemented in 12E:

- retry, `EXECUTION_UNKNOWN`, outbox, reconciliation
- production OAuth authorization/refresh
- managed secret stores
- automatic replies
- live Gmail/Graph send validation

### 12F — Failure Semantics, Privacy, Documentation & Regression

```text
12F
= failure semantics + privacy + documentation + regression

EXECUTION_UNKNOWN / retry / outbox / provider-result persistence
= not implemented
```

This slice consolidates the production failure model already implemented by 12C–12E. It does not add a new workflow state, schema, or reconciliation worker.

Authoritative failure matrix:

| Class | Examples | External request | HTTP | Stored status | Automatic retry |
|---|---|---|---|---|---|
| Pre-execution structural | targetless, missing/cross-user/disconnected account, unsupported provider, missing/malformed `credential_ref` | NO | 409 | APPROVED | NO |
| Pre-TX1 persistence unavailable | identity/DB failure before the `APPROVED` → `EXECUTING` commit | NO | 503 | previous (typically APPROVED) | NO |
| Confirmed success | Graph 202; Gmail profile 200 + metadata 200 + send 200 | YES | 200 | EXECUTED | NO |
| Definite external rejection | completed 3xx; non-408 4xx including 400/401/403/404/409/422/429 | YES | 200 | FAILED | NO |
| Token/secret unavailable after TX1 | valid locator; `AccessTokenProvider` fails | NO | 503 | EXECUTING | NO |
| Gmail pre-send unavailable after TX1 | profile/metadata timeout, 408, 5xx, transport, or malformed success | profile/metadata maybe; send POST = 0 | 503 | EXECUTING | NO |
| Side-effect uncertain after TX1 | Graph `/reply` or Gmail send timeout, transport, 408, 5xx, unexpected 2xx | YES (may or may not have been accepted) | 503 | EXECUTING | NO |

Missing mailbox secret after TX1 means the provider request did not occur. Gmail pre-send unavailable (profile/metadata) is not the same as send-outcome uncertain. Both remain `EXECUTING` after TX1 because no safe general retry/reconciliation protocol exists yet. Do not roll back to `APPROVED`. Do not automatically resend. Pre-TX1 persistence 503 did not reach the provider stage. See [ADR-020](../decisions/ADR-020-uncertain-communication-execution-semantics.md).

Phase 12 persists only workflow execution state (`EXECUTING` / `EXECUTED` / `FAILED`). It does not persist raw Graph or Gmail response bodies, sent-message ids, mailbox addresses, recipients, subjects, Message-IDs, MIME, tokens, or `credential_ref`. Graph 202 has no required body. Gmail 200 success is accepted without parsing the returned Message. Earlier "provider-result persistence" wording is therefore clarified as workflow-state persistence, not provider payload storage. Alembic head remains `12a0001`.

Implemented in this slice:

- ADR-020 uncertain external-side-effect semantics
- documentation of 200 FAILED versus 503 EXECUTING
- privacy/data-minimization consolidation
- architecture, API, and security documentation alignment
- regression hardening for uncertain outcomes, definite rejection, no re-execution, and marker privacy

Not implemented in 12F:

- `EXECUTION_UNKNOWN`
- automatic retry, backoff, or `Retry-After` resend
- outbox / execution-attempts / reconciliation worker
- raw provider-result persistence or success-response parsing for persistence
- schema migration
- production OAuth, token refresh, or managed secret stores
- automatic replies
- live provider send validation

## Deliverables

- [x] Phase 12A — Execution Target, Routing & Executability Foundation (completed)
- [x] Phase 12B — Credential Resolution + Write-Scope Readiness (completed)
- [x] Phase 12C — Microsoft Graph Reply Executor (completed)
- [x] Phase 12D — Gmail Reply Executor (completed)
- [x] Phase 12E — Execute API + communications:send (completed)
- [x] Phase 12F — Failure Semantics, Privacy, Documentation & Regression (completed)

## Deferred beyond Phase 12

- production OAuth authorization/refresh
- Azure Key Vault / AWS Secrets Manager mailbox secret backends
- operator reconciliation tooling
- execution-attempt / outbox model if later justified
- safe retry strategy if later justified
- `EXECUTION_UNKNOWN` if a richer attempt model is later justified
- live provider validation
- automatic replies
