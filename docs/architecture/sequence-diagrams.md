# Sequence Diagrams

These diagrams describe the request flows implemented as of Phase 10. Source `.mmd` files live in [`docs/diagrams/`](../diagrams/README.md); the communication-analysis HTTP flows are combined in [`request-flow.mmd`](../diagrams/request-flow.mmd). Persistence mapping is in [`persistence.mmd`](../diagrams/persistence.mmd). The sequence below uses `MockAIProvider` as the default local provider; `MicrosoftFoundryProvider` and `AmazonBedrockProvider` occupy the same `AIProvider` slot when selected. Connector adapters occupy the `CommunicationConnector` slot; vendor types do not appear above infrastructure.

## Successful Communication-Analysis Request (analyze-only)

When `DATABASE_URL` is omitted, or the caller is not an authenticated principal with persistence wired, analyze returns the AI result without `analysis_id`.

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route
    participant Workflow as CommunicationAnalysisWorkflowService
    participant Service as CommunicationAnalysisService
    participant Provider as AIProvider

    Client->>Route: POST /api/v1/communications/analyze
    Route->>Route: Validate CommunicationRequest (Pydantic)
    Route->>Workflow: analyze(request)
    Workflow->>Service: analyze(request)
    Service->>Provider: analyze(request)
    Provider-->>Service: CommunicationAnalysisResult
    Service-->>Workflow: CommunicationAnalysisResult
    Workflow-->>Route: result without analysis_id
    Route-->>Client: 200 OK + JSON body
```

## Persist-after-analyze (authenticated, persistence configured)

Identity uses a short transaction that commits before the AI call. Analysis save uses a new short transaction after inference.

```mermaid
sequenceDiagram
    participant Client
    participant Workflow as CommunicationAnalysisWorkflowService
    participant Identity as IdentityResolver
    participant Service as CommunicationAnalysisService
    participant History as AnalysisHistoryService

    Client->>Workflow: POST /api/v1/communications/analyze
    Workflow->>Identity: resolve_or_create (short TX)
    Identity-->>Workflow: user_id
    Workflow->>Service: analyze(request)
    Service-->>Workflow: CommunicationAnalysisResult
    Workflow->>History: save (new short TX)
    History-->>Workflow: analysis_id
    Workflow-->>Client: 200 OK including analysis_id
```

If save fails after a successful AI call, the workflow still returns HTTP 200 with the analysis and omits `analysis_id`. The provider is not retried.

## Connector ingestion → analysis (not an HTTP endpoint)

Phase 10 added no connector HTTP routes. This path exists below the product API. `CommunicationIngestionService` fetches one already-normalized message and reuses the existing workflow. Mailbox HTTP happens first, before workflow identity or history transactions. No database transaction is held open across the mailbox request or AI inference. When the workflow is constructed with an authenticated principal and persistence, it may persist a derived analysis (not raw mail) using the same short-transaction rules as HTTP analyze. Raw mailbox payloads are not persisted.

```mermaid
sequenceDiagram
    participant Mailbox as External mailbox API
    participant Connector as CommunicationConnector
    participant Ingestion as CommunicationIngestionService
    participant Workflow as CommunicationAnalysisWorkflowService
    participant Service as CommunicationAnalysisService
    participant Provider as AIProvider

    Ingestion->>Connector: fetch_message(provider_message_id)
    Connector->>Mailbox: vendor REST fetch
    Mailbox-->>Connector: vendor payload
    Connector-->>Ingestion: CommunicationMessage
    Ingestion->>Workflow: analyze(CommunicationRequest)
    Workflow->>Service: analyze(request)
    Service->>Provider: analyze(request)
    Provider-->>Service: CommunicationAnalysisResult
    Service-->>Workflow: CommunicationAnalysisResult
    Workflow-->>Ingestion: PersistedAnalysisOutcome
```

Vendor adapters (fake, Gmail REST, Microsoft Graph REST) implement `CommunicationConnector`. Application code never sees Gmail JSON, MIME, or Graph JSON.

This application path is covered by mocked ingestion-boundary tests. It is **not** a product-facing live-mailbox summary API.

### Controlled live adapter checks (not the application workflow)

Controlled local Gmail and Microsoft Graph verifications stopped at the connector/domain boundary:

```text
Gmail API / Microsoft Graph REST
        ↓
vendor CommunicationConnector adapter
        ↓
CommunicationMessage
        STOP
```

Those live checks did not call `CommunicationIngestionService`, `CommunicationAnalysisWorkflowService`, `AIProvider` (including Foundry, Bedrock, and `MockAIProvider`), PostgreSQL, or `connector_accounts`. They are not OAuth, send, reply, background-sync, or credential-resolver sequences.

The following are **not implemented** and are not shown as current flows: OAuth callback, credential resolver, background sync, automatic replies, sending.

## Identity failure before AI

```mermaid
sequenceDiagram
    participant Client
    participant Workflow as CommunicationAnalysisWorkflowService
    participant Identity as IdentityResolver
    participant Handler as Exception Handler

    Client->>Workflow: POST /api/v1/communications/analyze
    Workflow->>Identity: resolve_or_create
    Identity--xWorkflow: ServiceUnavailableError
    Workflow--xHandler: propagate
    Handler-->>Client: 503 Persistence is currently unavailable
```

No AI provider call is made.

## Provider Failure Flow

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(communications.py)
    participant Service as CommunicationAnalysisService
    participant Provider as AIProvider
    participant Handler as Exception Handler<br/>(app/main.py)

    Client->>Route: POST /api/v1/communications/analyze
    Route->>Route: Validate CommunicationRequest (Pydantic)
    Route->>Service: analyze(request)
    Service->>Provider: analyze(request)
    Provider--xService: raises Exception
    Service->>Service: log communication_analysis_failed
    Service--xRoute: raises AnalysisFailedError
    Route--xHandler: propagates ECIPlatformError
    Handler->>Handler: log application_error
    Handler-->>Client: 500 + {"detail": "..."}
```

## Configuration Error Flow (Unsupported Provider)

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(communications.py)
    participant Dep as get_ai_provider (dependency)
    participant Factory as create_ai_provider
    participant Handler as Exception Handler<br/>(app/main.py)

    Client->>Route: POST /api/v1/communications/analyze
    Route->>Dep: resolve CommunicationAnalysisService
    Dep->>Factory: create_ai_provider(settings)
    Factory--xDep: raises ConfigurationError (unsupported AI_PROVIDER)
    Dep--xRoute: propagates ConfigurationError
    Route--xHandler: propagates ECIPlatformError
    Handler-->>Client: 500 + {"detail": "Unsupported AI provider '...'. Supported providers: mock, microsoft_foundry, amazon_bedrock"}
```

## Health and Readiness

`GET /health` is process liveness only. `GET /api/v1/readiness` probes the database with `SELECT 1` only when `DATABASE_URL` is configured.

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(health.py)
    participant Settings as Settings (app/core/config.py)
    participant Probe as Database readiness probe

    Client->>Route: GET /health
    Route-->>Client: 200 OK + {"status": "healthy"}

    Client->>Route: GET /api/v1/health
    Route->>Settings: get_settings()
    Settings-->>Route: app_name, app_version, app_env
    Route-->>Client: 200 OK + HealthResponse

    Client->>Route: GET /api/v1/readiness
    Route->>Settings: get_settings()
    alt Persistence disabled
        Route-->>Client: 200 OK + {"status": "ready"}
    else Persistence configured and healthy
        Route->>Probe: SELECT 1
        Probe-->>Route: ok
        Route-->>Client: 200 OK + {"status": "ready"}
    else Persistence configured and unavailable
        Route->>Probe: SELECT 1
        Probe--xRoute: failure
        Route-->>Client: 503 Persistence is currently unavailable
    end
```

Health never queries PostgreSQL. Readiness does not leak database details.

## Authenticated Analyze Request (`AUTH_MODE=oidc`)

When `AUTH_MODE=oidc`, analyze requires a bearer token. Missing or invalid tokens return `401`. A valid token with permission `communications:analyze` continues to the workflow.

```mermaid
sequenceDiagram
    participant Client
    participant Dep as TokenValidator
    participant Route as FastAPI Route
    participant Workflow as CommunicationAnalysisWorkflowService

    Client->>Dep: POST /api/v1/communications/analyze (no token)
    Dep-->>Client: 401 Unauthorized

    Client->>Dep: POST /api/v1/communications/analyze<br/>Authorization Bearer JWT
    Dep->>Dep: validate iss, aud, exp, JWKS
    Dep->>Dep: require communications:analyze
    Dep->>Route: AuthenticatedPrincipal
    Route->>Workflow: analyze(request)
    Workflow-->>Route: PersistedAnalysisOutcome
    Route-->>Client: 200 OK
```

## Owned history request

Unknown and cross-user analysis ids both return `404`. History always requires an authenticated principal (`AUTH_MODE=disabled` returns `401`). Missing `DATABASE_URL` returns `503`.

```mermaid
sequenceDiagram
    participant Client
    participant Route as Analyses route
    participant Identity as IdentityResolver
    participant History as AnalysisHistoryService

    Client->>Route: GET /api/v1/analyses/{analysis_id}
    Route->>Identity: find_existing(issuer, subject)
    alt No mapping or not owned
        Route-->>Client: 404 Analysis not found
    else Owned by caller
        Route->>History: get_for_user(analysis_id, user_id)
        History-->>Route: AnalysisRecord
        Route-->>Client: 200 AnalysisHistoryItem
    end
```

## Workflow action lifecycle (Phase 11B, no HTTP)

Phase 11B persists user-owned workflow actions. There are still no workflow routes. The domain state machine is:

```text
PENDING → APPROVED → EXECUTING → EXECUTED
PENDING → REJECTED
EXECUTING → FAILED
```

```mermaid
sequenceDiagram
    participant Analysis as CommunicationAnalysis
    participant Draft as DraftReply
    participant Action as WorkflowAction

    Note over Analysis,Draft: Analyze produces suggestions only
    Analysis->>Draft: draft_reply body
    Note over Action: Explicit later construction; not created by analyze
    Action->>Action: PENDING (proposed_reply_body snapshotted)
    alt Human approves
        Action->>Action: APPROVED (approved_reply_body = proposed_reply_body)
        Action->>Action: EXECUTING
        alt Later execution success
            Action->>Action: EXECUTED
        else Later execution failure
            Action->>Action: FAILED
        end
    else Human rejects
        Action->>Action: REJECTED
    end
```

Authorization is capability-specific after JWT authentication:

```text
authenticate JWT → AuthenticatedPrincipal → required permission
communications:analyze     (existing analyze / history)
communications:workflow    (future workflow HTTP; checkable in 11A)
```
