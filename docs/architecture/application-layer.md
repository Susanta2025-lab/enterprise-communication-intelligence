# Application Layer

The application layer (`app/application/`) orchestrates use cases. `CommunicationAnalysisService` remains the AI-only analysis service. Phase 9 adds workflow, identity, and history services around it without putting SQLAlchemy in the application layer. Phase 10 adds `CommunicationIngestionService` and `ConnectorAccountService` without putting vendor mailbox types or OAuth in the application layer. Phase 11B adds `WorkflowActionService` for durable approval-gated reply actions. Phase 11C exposes that service over HTTP. Phase 11D adds `WorkflowActionExecutionService` for execute-after-approval through `CommunicationActionExecutor`. `CommunicationAnalysisWorkflowService` remains persist-after-analyze orchestration.

## Role of `CommunicationAnalysisService`

The service is the single AI orchestration point between the workflow/API and the AI provider abstraction. It:

1. Receives an already-validated `CommunicationRequest` (validation happens in the Pydantic domain models before the service is ever called).
2. Delegates analysis to the injected `AIProvider`.
3. Returns the provider's `CommunicationAnalysisResult` unchanged on success.
4. Translates any provider exception into `AnalysisFailedError`.
5. Emits structured logs at each stage.

It does not resolve users, open database transactions, or store history.

## Constructor Injection

```python
service = CommunicationAnalysisService(provider)
```

The service's `__init__` takes exactly one dependency — an `AIProvider` — and stores it as `self._provider`. It never constructs a provider itself and never imports `app.providers.factory`. The API layer (`app/api/dependencies.py`) is responsible for resolving the provider via the factory and passing it in.

## Orchestration Responsibility

`analyze(request: CommunicationRequest) -> CommunicationAnalysisResult` is the service's only public method. Its orchestration is intentionally linear:

```python
def analyze(self, request):
    logger.info("communication_analysis_started", ...)
    try:
        result = self._provider.analyze(request)
    except Exception as exc:
        logger.error("communication_analysis_failed", ...)
        raise AnalysisFailedError(...) from exc
    logger.info("communication_analysis_completed", ...)
    return result
```

There is no branching on provider type, no retry logic, and no additional business rules layered on top of the provider's output — the service trusts the domain models to have already validated the request, and trusts the provider to produce a valid `CommunicationAnalysisResult`.

## Persistence-aware workflow

`CommunicationAnalysisWorkflowService` wraps the AI service when persistence and an authenticated principal are present. That name predates Phase 11. It is **not** the approval-gated `WorkflowAction` service.

```text
authenticate / authorize
→ IdentityResolver.resolve_or_create (short DB transaction)
→ commit / close
→ CommunicationAnalysisService.analyze (AI provider call)
→ AnalysisHistoryService.save (new short DB transaction)
```

No database transaction is held across the AI provider network call. Identity/database failure before AI returns HTTP `503` with zero provider calls. AI success plus save failure returns HTTP `200` with the analysis and omits `analysis_id`; the provider is not retried.

When `DATABASE_URL` is omitted, or the caller is unauthenticated in development, the workflow calls the AI service and returns no `analysis_id`.

See [Persistence](persistence.md).

## Identity and history services

- `IdentityResolver` maps verified OIDC `issuer` + `subject` to an opaque internal `users.id` UUID. It does not persist email, name, JWT, or tokens.
- `AnalysisHistoryService` saves, lists, gets, and deletes analyses through `AnalysisRepository`. Every query is SQL-scoped by `user_id`. Unknown and cross-user resources raise `AnalysisNotFoundError` (`404`).

These services depend on `PersistenceUnitOfWork` and repository interfaces in `app/domain/interfaces/`, not on SQLAlchemy models.

## Communication ingestion

`CommunicationIngestionService` is the application entry for a connector-supplied message. It:

```text
CommunicationConnector.fetch_message
→ CommunicationMessage
→ CommunicationRequest
→ CommunicationAnalysisWorkflowService.analyze(..., connector_account_id=...)
```

`connector_account_id` is optional constructor context from an already owned connector account. The generic `POST /api/v1/communications/analyze` path never supplies it. Unowned account ids are rejected at analysis save and do not enter persistence. Analysis provenance is not execution eligibility: save does not require `ACTIVE`. A later disconnect does not rewrite stored analysis provenance.

It does **not**:

- own OAuth, refresh tokens, or consent
- call `AIProvider` directly
- persist raw mail
- resolve `credential_ref`
- interpret vendor cursors or pagination tokens
- import Gmail or Microsoft Graph types

Identity, optional analysis persistence, and AI orchestration remain on `CommunicationAnalysisWorkflowService` and `CommunicationAnalysisService`. Connector HTTP routes are not present; callers construct a connector and this service below the API.

## Connector accounts

`ConnectorAccountService` (`app/application/services/connector_accounts.py`) manages the user-owned connector-account lifecycle:

- bind an authenticated principal to an internal `users.id`
- register, list, retrieve, and disconnect accounts
- store provider identity and opaque `external_account_id`
- accept optional opaque `credential_ref` without treating it as token material

It does **not** store access tokens, refresh tokens, authorization codes, or secrets. It does not call Gmail, Microsoft Graph, or `AIProvider`. Application-facing `ConnectorAccountResult` omits `user_id` and `credential_ref`. Credential resolution is a separate domain port (`CommunicationCredentialResolver`) implemented in infrastructure; `ConnectorAccountService` does not perform it.

## Credential resolution

`CommunicationCredentialResolver` (`app/domain/interfaces/communication_credential_resolver.py`) translates an opaque `credential_ref` plus mailbox `provider` into an on-demand `AccessTokenProvider`. It does not decide account ownership, workflow executability, or which message to reply to.

`EnvironmentCommunicationCredentialResolver` (`app/infrastructure/credentials/environment.py`) is the local/development implementation. It maps `(provider, credential_ref)` to `ECI_COMMUNICATION_CREDENTIAL_<PROVIDER>_<NORMALIZED_REF>_ACCESS_TOKEN`. `credential_ref` is not unique on `ConnectorAccount`, so the provider slug is part of the secret key. Locators may use hyphens but not underscores, so hyphen-to-underscore encoding cannot collide. Secret lookup happens when the returned callable is invoked. Mailbox tokens are not loaded into `Settings`. Missing mailbox environment variables do not prevent startup. `WorkflowActionExecutionService` does not call the resolver; fake execution remains credential-independent. This is not production OAuth, refresh, Azure Key Vault, or AWS Secrets Manager.

## Provider Failure Translation

If `self._provider.analyze(request)` raises any exception, the AI service:

- Logs `communication_analysis_failed` with the configuration provider name (`PROVIDER_NAME` when present), the message ID (if present), `duration_ms`, and `error_class` — never the message body or `str(exc)`.
- Raises `AnalysisFailedError` with the provider's Python class name in the HTTP detail (for example `MockAIProvider`), using `raise ... from exc` to preserve the original cause internally without exposing it externally. Operational logs use `PROVIDER_NAME` and `error_class`; the HTTP `detail` does not.

This keeps the API layer's exception handling simple: it only needs to know about `ECIPlatformError` and its subclasses, never about what a specific provider might raise.

## Structured Logging

Three structured log events are emitted by the AI service, all via `app.core.logging.get_logger(__name__)`:

| Event | Level | Fields |
|---|---|---|
| `communication_analysis_started` | info | `provider`, `message_id`, `source_type` |
| `communication_analysis_completed` | info | `provider`, `message_id`, `priority`, `category`, `duration_ms` |
| `communication_analysis_failed` | error | `provider`, `message_id`, `duration_ms`, `error_class` |

`provider` is the configuration name (`mock`, `microsoft_foundry`, `amazon_bedrock`) when the adapter exposes `PROVIDER_NAME`. HTTP middleware binds `request_id` for the same request. None of these log the communication body, subject, sender, recipient, prompt, model output, credentials, or raw exception messages. Persistence logs use `error_class` and operation names; they do not log `DATABASE_URL`, identity values, or message bodies. See [Observability](../cloud/observability.md).

## Statelessness

`CommunicationAnalysisService` holds only a reference to its injected provider (`self._provider`); it has no other instance state. A single instance can safely handle repeated, unrelated `analyze()` calls — this is verified in `tests/unit/application/test_communication_analysis_service.py` (`test_service_remains_stateless_across_requests`).

## What the AI Service Deliberately Does Not Do

- **No HTTP work.** It never imports `fastapi`, builds a `Response`, or reads request headers.
- **No environment or configuration access.** It never calls `get_settings()` or reads an environment variable; provider selection happens entirely upstream, in `app/api/dependencies.py` and `app/providers/factory.py`.
- **No provider instantiation.** It never calls `create_ai_provider()` or imports a concrete provider class.
- **No persistence.** Results are stored by `AnalysisHistoryService` after the AI call returns. The AI service remains a request/response orchestrator.
- **No workflow actions.** Analyze does not create `WorkflowAction` records. `DraftReply` stays suggestion output.

## Workflow actions

`WorkflowActionService` (`app/application/services/workflow_actions.py`) is the Phase 11B application service:

```text
AuthenticatedPrincipal
→ IdentityResolver.find_existing
→ owned analysis (create only)
→ snapshot draft_reply.body
→ WorkflowActionRepository
```

Public operations are create, get, list, approve, and reject. Create requires an owned analysis with a usable draft reply. Create snapshots a complete mailbox execution target from `analysis.connector_account_id` and `analysis.message_id` when both are present; otherwise both workflow fields stay `NULL`. Approve and reject load the owned `WorkflowAction` only; they do not reload the analysis, call an AI provider, or alter routing provenance. Approval copies `proposed_reply_body` into `approved_reply_body`. Missing identity mappings use the same not-found semantics as other owned resources; list returns an empty page.

The service depends on `PersistenceUnitOfWork` and `WorkflowActionRepository`. It does not import SQLAlchemy models, FastAPI, Gmail/Graph adapters, or an executor. Phase 11C maps those operations to HTTP in `app/api/routes/workflow_actions.py` without duplicating service logic.

## Workflow action execution

`WorkflowActionExecutionService` (`app/application/services/workflow_action_execution.py`) is the Phase 11D execution orchestrator. It is not an extension of `WorkflowActionService`.

```text
AuthenticatedPrincipal
→ IdentityResolver.find_existing
→ TX1: validate execution target and owned active ConnectorAccount,
  then owned APPROVED → EXECUTING, commit, close UoW
→ CommunicationActionExecutor.execute(CommunicationActionExecution)
→ TX2: EXECUTING → EXECUTED or FAILED, commit
```

Constructor injection supplies `IdentityResolver`, a unit-of-work factory, and a `CommunicationActionExecutor`. There is no executor factory, no `ACTION_EXECUTOR` setting, and no FastAPI `get_workflow_action_execution_service` dependency because there is no HTTP execute route.

The executor command is the approved snapshot (`approved_reply_body`) plus provider-neutral routing (`connector_account_id`, `provider_message_id`, `provider` from the owned `ConnectorAccount`). It is not `proposed_reply_body` and not a reloaded analysis draft. Analysis hard-delete does not block execution. Targetless, missing, cross-user, and disconnected accounts raise `WorkflowActionNotExecutableError` inside the execution unit of work before the `APPROVED` → `EXECUTING` write, TX1 commit, or executor call. `ACTIVE` is structural executability in 12A; `credential_ref` is not inspected. Known `CommunicationActionExecutionError` becomes durable `FAILED`. Unexpected executor exceptions are not converted into `FAILED`; the row may remain `EXECUTING`.

Phase 12A still uses `FakeCommunicationActionExecutor` as the injected workflow executor. Phase 12C adds `MicrosoftGraphCommunicationActionExecutor` under `app/infrastructure/executors/` without injecting it here. `CommunicationConnector` remains read-only. Gmail writes remain later work. Phase 12B adds `CommunicationCredentialResolver` without injecting it into this service.
