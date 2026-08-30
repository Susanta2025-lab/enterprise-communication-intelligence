# Error Handling

This describes the error handling actually implemented in `app/main.py`, `app/core/exceptions.py`, and `app/application/exceptions.py`.

## Validation Errors (Pydantic/FastAPI)

Requests that fail Pydantic model validation (e.g. empty `body`, invalid `source_type`, missing required fields, or unexpected fields — all domain models use `extra="forbid"`) are rejected by FastAPI's default `RequestValidationError` handling before any application code runs.

- **Status code:** `422 Unprocessable Entity`
- **Body shape:** FastAPI's default validation error format, an array of error objects under `"detail"`, each with `type`, `loc`, `msg`, and `input`.

This is FastAPI's built-in behavior; no custom validation error handler is registered in `app/main.py`.

## Application Exception Hierarchy

Defined in `app/core/exceptions.py`:

```python
class ECIPlatformError(Exception):
    """Base error for all ECI Platform application failures."""

class ConfigurationError(ECIPlatformError):
    """Raised when application configuration is invalid or incomplete."""

class ServiceUnavailableError(ECIPlatformError):
    """Raised when a required service dependency is unavailable."""
```

`app/application/exceptions.py` adds application-layer exceptions:

```python
class AnalysisFailedError(ECIPlatformError):
    """Raised when an AI provider fails to analyze a communication."""

class AnalysisNotFoundError(ECIPlatformError):
    """Raised when an analysis is unknown or not owned by the caller."""

class WorkflowActionNotFoundError(ECIPlatformError):
    """Raised when a workflow action is unknown or not owned by the caller."""

class WorkflowActionConflictError(ECIPlatformError):
    """Raised when a conditional workflow update no longer matches stored status."""

class AnalysisHasNoDraftReplyError(ECIPlatformError):
    """Raised when an owned analysis has no usable draft reply to snapshot."""
```

`ConnectedMailboxNotAvailableError`, `MailboxMessageNotFoundError`, and `MailboxPaginationCursorInvalidError` are also defined on `app/application/exceptions.py`. The first covers an owned connector account that cannot currently be used for mailbox read or mailbox-backed analyze without distinguishing DISCONNECTED, `REAUTH_REQUIRED`, missing `mail.read`, unsupported provider, or missing locator. Confirmed permanent OAuth refresh failure uses that same 409 after persisting `ACTIVE → REAUTH_REQUIRED` for the exact owned account (`credential_ref` and grants preserved). Transient credential-store, refresh, network, provider 5xx, and mailbox HTTP 401/403 after a valid token remain `ServiceUnavailableError` (503) and do not mutate lifecycle. The second is the public not-found type for a provider message id. The third is the public client error when a connector identifies an invalid or expired list cursor. Cross-user connector existence remains `ConnectorAccountNotFoundError`. Phase 14C/14D/14E map connector/credential failures onto these types plus existing sanitized 500s; they do not expose provider payloads, tokens, locators, or database text in public error text.

`app/domain/exceptions.py` defines `InvalidWorkflowTransitionError` with message `"Invalid workflow state transition."`. It is not an `ECIPlatformError` subclass and has a dedicated HTTP handler.

`PersistenceError` is also defined on `app/core/exceptions.py`. All of these carry a plain `.message: str` and no additional context, stack trace, or provider internals.

## Registered Exception Handlers (`app/main.py`)

Exception handlers are registered on the FastAPI app:

| Exception type | Status code | Response body | Logged event |
|---|---|---|---|
| `AnalysisNotFoundError` | `404` | `{"detail": "Analysis not found."}` | `analysis_not_found` (info) |
| `WorkflowActionNotFoundError` | `404` | `{"detail": "Workflow action not found."}` | `workflow_action_not_found` (info) |
| `AnalysisHasNoDraftReplyError` | `409` | `{"detail": "Analysis has no usable draft reply."}` | `analysis_has_no_draft_reply` (info) |
| `InvalidWorkflowTransitionError` | `409` | `{"detail": "Invalid workflow state transition."}` | `invalid_workflow_transition` (info) |
| `WorkflowActionConflictError` | `409` | `{"detail": "Workflow action was updated concurrently."}` | `workflow_action_conflict` (warning) |
| `WorkflowActionNotExecutableError` | `409` | `{"detail": "Workflow action is not executable."}` | `workflow_action_not_executable` (info) |
| `MailboxAuthorizationSessionInvalidError` | `400` | `{"detail": "Mailbox authorization session is invalid."}` | `mailbox_authorization_session_invalid` (info) |
| `MailboxOAuthAuthorizationDeniedError` | `400` | `{"detail": "Mailbox authorization was denied."}` | `mailbox_oauth_authorization_denied` (info) |
| `MailboxOAuthAuthorizationFailedError` | `400` | `{"detail": "Mailbox authorization failed."}` | `mailbox_oauth_authorization_failed` (info) |
| `ConnectorAccountNotFoundError` | `404` | `{"detail": "Connector account not found."}` | `connector_account_not_found` (info) |
| `ConnectorAccountConflictError` | `409` | `{"detail": "Connector account cannot be updated."}` | `connector_account_conflict` (info) |
| `ConnectedMailboxNotAvailableError` | `409` | `{"detail": "Connected mailbox is not available."}` | `connected_mailbox_not_available` (info) |
| `MailboxMessageNotFoundError` | `404` | `{"detail": "Mailbox message not found."}` | `mailbox_message_not_found` (info) |
| `MailboxPaginationCursorInvalidError` | `400` | `{"detail": "Mailbox pagination cursor is invalid."}` | `mailbox_pagination_cursor_invalid` (info) |
| `PersistenceError` | `503` | `{"detail": "Persistence is currently unavailable."}` | `persistence_unavailable` (warning) |
| `ServiceUnavailableError` | `503` | `{"detail": exc.message}` | `service_unavailable` (warning) |
| `ECIPlatformError` (and any subclass not more specifically registered) | `500` | `{"detail": exc.message}` | `application_error` (error) |

Because Starlette/FastAPI matches exception handlers by most-specific registered type, `ConfigurationError` and `AnalysisFailedError` — which have no dedicated handler — are both caught by the `ECIPlatformError` handler and return `500`.

Authentication and authorization failures are raised as FastAPI `HTTPException` values from `app/api/dependencies.py`. They are not `ECIPlatformError` subclasses and therefore are not mapped to `500`.

## Authentication and Authorization Errors

When `AUTH_MODE=oidc`, analyze requires a bearer token. History and workflow routes always require an authenticated principal; `AUTH_MODE=disabled` returns `401` for those routes. Responses:

| Condition | Status | `WWW-Authenticate` | Body |
|---|---|---|---|
| Missing bearer token | `401` | `Bearer` | `{"detail": "Not authenticated"}` |
| Invalid, expired, wrong issuer/audience, or bad signature | `401` | `Bearer` | `{"detail": "Not authenticated"}` |
| Valid token without the route permission | `403` | not set | `{"detail": "Not authorized"}` |
| Unknown or cross-user `analysis_id` | `404` | not set | `{"detail": "Analysis not found."}` |
| Unknown or cross-user workflow action | `404` | not set | `{"detail": "Workflow action not found."}` |
| Unknown or cross-user connector account | `404` | not set | `{"detail": "Connector account not found."}` |
| Provider message unknown for an owned mailbox | `404` | not set | `{"detail": "Mailbox message not found."}` |
| Owned connector account not currently usable for mailbox read/analyze | `409` | not set | `{"detail": "Connected mailbox is not available."}` |

Analyze and history require `communications:analyze`. Workflow proposal/approval routes require `communications:workflow`. Execute requires `communications:send`. Gmail and Microsoft mailbox authorize (including connect-another), disconnect, and reauthorize require `communications:connect`. Bounded mailbox listing requires `communications:read`. Mailbox-backed analyze requires `communications:read` and `communications:analyze`. Direct-text analyze does not require `communications:read`. The Google and Microsoft callbacks do not use the ECI bearer token. None of those permissions implies another. `communications:workflow` does not authorize external sending.

Bounded failure reasons are written to structured logs only (`missing_token`, `invalid_token`, `expired_token`, `invalid_issuer`, `invalid_audience`, `unknown_signing_key`, `insufficient_permission`). JWT library exception text is not returned or logged.

## Configuration Errors

If `AI_PROVIDER` is set to an unsupported value, `app/providers/factory.py` raises:

```text
ConfigurationError("Unsupported AI provider '<value>'. Supported providers: mock, microsoft_foundry, amazon_bedrock")
```

This is raised during dependency resolution (`get_ai_provider` in `app/api/dependencies.py`), before the route body executes, and is translated into a `500` response by the `ECIPlatformError` handler. There is no silent fallback to another provider.

## Provider/Service Failures

If the injected `AIProvider.analyze(...)` call raises any exception, `CommunicationAnalysisService.analyze(...)` (`app/application/services/communication_analysis.py`):

1. Logs `communication_analysis_failed` with the provider name, message ID, `duration_ms`, and `error_class` (never the message body or `str(exc)`).
2. Raises `AnalysisFailedError("AI provider '<ProviderClassName>' failed to analyze the communication.")`, chained via `raise ... from exc` so the original exception is preserved as the Python `__cause__` internally — it is not exposed in the HTTP response.

The HTTP `detail` still uses the provider's Python class name (for example `MockAIProvider`). Operational logs use the configuration provider name and `error_class`.

This is translated by the `ECIPlatformError` handler into a `500` response.

## Persistence Failures

Identity or database failure before AI is translated to `503` with `{"detail": "Persistence is currently unavailable."}` and does not call the AI provider.

AI success plus history save failure returns HTTP `200` with the analysis and omits `analysis_id`. The provider is not retried.

History get/delete of an unknown or cross-user id returns `404` with `{"detail": "Analysis not found."}`, not `403`.

Workflow create against an unknown or cross-user analysis returns the same analysis `404`. Workflow get/approve/reject/execute of an unknown or cross-user action returns `404` with `{"detail": "Workflow action not found."}`. Create against an owned analysis with no usable draft returns `409`. Invalid approve/reject/execute transitions return `409` with `{"detail": "Invalid workflow state transition."}`. Concurrent updates return `409` with `{"detail": "Workflow action was updated concurrently."}`. Not-executable execute attempts return `409` with `{"detail": "Workflow action is not executable."}`. Execute without persistence before TX1 returns `503` with the previous workflow state unchanged; execution did not reach the provider stage. A missing mailbox secret after `EXECUTING` returns `503` with stored `EXECUTING`; the provider request did not occur. An uncertain provider outcome after TX1 also returns `503` with stored `EXECUTING`. Workflow routes without persistence return the same generic `503` body.

Readiness returns the same generic `503` body when persistence is configured and the database probe fails. Database host, driver, and SQL details are not returned.

## Safe Error-Response Behavior

- Responses only ever contain `{"detail": "<message>"}` for application exceptions — no stack traces, no exception class names, no provider SDK details.
- The `AnalysisFailedError` message includes only the provider's Python class name (e.g. `MockAIProvider`) and a generic failure statement, not the underlying exception's message or traceback.
- `ConfigurationError` messages mention the configured (invalid) provider name and the list of currently supported providers (`mock`, `microsoft_foundry`) — this is intentional operator-facing feedback, not a security-sensitive detail, but it is documented here for completeness.

## Status Code Summary

| Status | Meaning | Source |
|---|---|---|
| `200` | Successful request | Normal route return. Analyze may omit `analysis_id` after a post-inference save failure. Workflow approve/reject/execute return the updated action. Execute 200 + `failed` is a recorded definite provider rejection. |
| `201` | Workflow action created | `POST /api/v1/workflow-actions` |
| `204` | Owned analysis deleted | `DELETE /api/v1/analyses/{analysis_id}` |
| `401` | Missing or invalid bearer token | Analyze when `AUTH_MODE=oidc`; history, workflow, execute, mailbox listing, mailbox-backed analyze, and Gmail/Microsoft authorize always (`AUTH_MODE=disabled` included). The Google and Microsoft callbacks are public. |
| `403` | Authenticated token lacks the route permission | `communications:analyze` for analyze/history; `communications:workflow` for proposal/approval; `communications:send` for execute; `communications:connect` for Gmail/Microsoft authorize, disconnect, and reauthorize; `communications:read` for mailbox listing; `communications:read` and `communications:analyze` for mailbox-backed analyze |
| `400` | Mailbox OAuth or pagination failure | Invalid/expired/consumed state, Google consent denial, sanitized authorization failure, or invalid mailbox list cursor |
| `404` | Resource unknown or not owned by the caller | `AnalysisNotFoundError`, `WorkflowActionNotFoundError`, `ConnectorAccountNotFoundError`, or `MailboxMessageNotFoundError` |
| `409` | Workflow or mailbox conflict | No usable draft, invalid transition, concurrent update, not executable, re-execute of EXECUTING/EXECUTED/FAILED, connector account not reauthorizable, or owned mailbox not currently usable for read/analyze |
| `422` | Request failed schema validation | FastAPI/Pydantic default behavior |
| `500` | Application or configuration error (`ECIPlatformError` and subclasses, including `ConfigurationError`, `AnalysisFailedError`) | `app/main.py` exception handler |
| `503` | Persistence unavailable, missing mailbox secret after `EXECUTING` (provider request did not occur), uncertain provider outcome, or readiness probe failure (`ServiceUnavailableError` / `PersistenceError`). Execute 503 after TX1 leaves the row `EXECUTING`; do not retry automatically. Persistence failure before TX1 leaves the prior status unchanged and does not reach the provider. Not every 503 means a send may have occurred. | `app/main.py` exception handlers |
