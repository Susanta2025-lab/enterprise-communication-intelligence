# Architecture Overview

## Implemented Request Path

HTTP product surface:

```text
Client
  ↓
FastAPI REST API        (app/api)
  ↓
CommunicationAnalysisWorkflowService   (app/application/services)
  ├── IdentityResolver → users / external_identities
  ├── CommunicationAnalysisService → AIProvider
  └── AnalysisHistoryService → AnalysisRepository → PostgreSQL
```

Workflow HTTP product surface (proposal, approval, and execute):

```text
Client
  ↓
FastAPI REST API
  ↓
WorkflowActionService | WorkflowActionExecutionService
  ├── IdentityResolver.find_existing
  └── WorkflowActionRepository / owned ConnectorAccount → factory → Graph or Gmail
```

Execute is user-approved only:

```text
POST /api/v1/workflow-actions/{action_id}/execute
  → communications:send
  → TX1: validate owned APPROVED action and owned ACTIVE account, select executor, APPROVED → EXECUTING
  → executor.execute (no open UoW)
  → TX2 EXECUTED | FAILED
```

Connector ingestion path (below the HTTP product surface; no connector routes). Vendor adapters call Gmail or Microsoft Graph REST and implement the domain port:

```text
CommunicationConnector
        ↑
vendor adapter (fake / Gmail REST / Microsoft Graph REST)
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

High-level layering:

```text
API
  → Application
    → Domain
      ← Infrastructure Storage
      ← Infrastructure Communication Connectors
      ← Infrastructure Executors
      ← AI Providers
```

`CommunicationAnalysisService` remains AI-only. Connector adapters return already-normalized `CommunicationMessage` values and do not call `AIProvider`. Persistence is optional in development when `DATABASE_URL` is omitted. Every layer is exercised by tests spanning `tests/unit`, `tests/integration`, and GitHub `tests/postgres`. Automated tests stay offline; Microsoft Foundry and Amazon Bedrock are exercised through mocked SDK clients. Live ECI → Bedrock verification is complete. PostgreSQL dialect coverage is proven in CI, not against a managed cloud database. Controlled local live Gmail and Graph checks stopped at `CommunicationMessage` and did not call AI or persistence.

## Purpose of Each Layer

- **FastAPI REST API (`app/api`)** — HTTP transport. Defines routes (`app/api/routes/`), the API router assembly (`app/api/router.py`), and dependency wiring (`app/api/dependencies.py`). Contains no business logic; every route validates input via Pydantic and delegates to a service. Phase 10 added no connector message-ingestion HTTP endpoints. Phase 11C adds workflow proposal and approval routes. Phase 12E adds execute. Phase 13 adds Gmail/Microsoft authorize, unauthenticated callbacks, disconnect, and reauthorize. Analyze/history keep `communications:analyze`; proposal/approval require `communications:workflow`; execute requires `communications:send`; mailbox connect/disconnect/reauthorize require `communications:connect`. Phase 14A adds `communications:read` for future mailbox listing; mailbox-backed analyze will require read and analyze. Direct-text analyze does not require read. The API does not import concrete Gmail or Graph executor classes.
- **Application service (`app/application`)** — Orchestrates use cases. `CommunicationAnalysisService` remains AI-only. `CommunicationAnalysisWorkflowService` resolves internal user ownership, calls the AI service, then persists through `AnalysisHistoryService`. `CommunicationIngestionService` fetches one `CommunicationMessage` from a `CommunicationConnector` and delegates to the existing workflow. `ConnectorAccountService` manages user-owned connector accounts with opaque `credential_ref`. `WorkflowActionService` manages proposal/approval lifecycle. `WorkflowActionExecutionService` commits `EXECUTING` then calls `CommunicationActionExecutor` with no open unit of work. Application code depends on domain interfaces, not SQLAlchemy or vendor mailbox types.
- **Domain (`app/domain`)** — Provider-independent business objects: enums (`SourceType`, `PriorityLevel`, `MessageCategory`, `ConnectorAccountStatus`, `WorkflowActionType`, `WorkflowActionStatus`), models (`CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`, `WorkflowAction`), schemas (`CommunicationRequest`, `CommunicationAnalysisResult`), the `AIProvider` interface, the `CommunicationConnector` contract, the `CommunicationActionExecutor` write port, and persistence repository/UoW interfaces. Domain code imports neither FastAPI, SQLAlchemy, nor any cloud SDK.
- **Providers (`app/providers`)** — Concrete implementations of `AIProvider`. `MockAIProvider`, `MicrosoftFoundryProvider`, and `AmazonBedrockProvider` are implemented. The two real LLM adapters share `app/providers/common/`. `app/providers/factory.py` selects a provider from configuration. Connector adapters do not live here and do not implement `AIProvider`.
- **Core (`app/core`)** — Cross-cutting concerns: `config.py` (Pydantic Settings, including `DATABASE_URL`), `logging.py` (structlog configuration), `telemetry.py` (request-safe `duration_ms` and `error_class` helpers), `exceptions.py` (the base application exception hierarchy, including `PersistenceError` and connector-neutral errors), `security.py` (OIDC JWT validation, `AuthenticatedPrincipal`, and capability-specific `authorize(principal, required_permission)`). HTTP `request_id` binding lives in `app/api/middleware.py`.
- **Infrastructure storage (`app/infrastructure/storage`)** — SQLAlchemy models, engine, unit of work, and repository implementations, including `connector_accounts`. Domain and application code do not import these types except through API dependency wiring.
- **Infrastructure communication connectors (`app/infrastructure/connectors`)** — Vendor adapters that implement `CommunicationConnector`: fake, Gmail REST v1, and Microsoft Graph REST v1.0. They normalize email to `SourceType.EMAIL` while keeping provider identity (`gmail`, `microsoft_graph`) separate. They do not persist raw mail, call `AIProvider`, own OAuth, resolve `credential_ref`, or expose HTTP routes.
- **Infrastructure executors (`app/infrastructure/executors`)** — Write-port adapters. `FakeCommunicationActionExecutor` remains the isolated test double. `ProviderCommunicationActionExecutorFactory` selects `MicrosoftGraphCommunicationActionExecutor` or `GmailCommunicationActionExecutor` from an owned account. Gmail discovers sender identity from `users/me/profile`. The fake provider is not production-routed.

## Provider Independence

The application service and every layer above it depend only on `app.domain.interfaces.AIProvider`, never on `MockAIProvider`, `MicrosoftFoundryProvider`, `AmazonBedrockProvider`, or any other concrete provider class. Provider selection happens in exactly one place — `app/providers/factory.py` — driven by the `AI_PROVIDER` setting. This means:

- Swapping providers requires no change to `CommunicationAnalysisService` or any route.
- Amazon Bedrock was added as `app/providers/amazon_bedrock/` plus one factory branch, without changing application or API code.

`CommunicationIngestionService` depends only on `CommunicationConnector`, never on Gmail or Graph types. There is no connector factory in the repository. Adapters are constructed by callers (tests and future composition), not by the API.

## Current Implementation Boundary

The system is fully synchronous. Through Phase 8 the runtime was stateless with respect to application data. Phase 9 adds optional persistence when `DATABASE_URL` is configured; omitting it keeps analyze-only behavior. Phase 10 adds vendor-neutral communication connectors below the HTTP surface. When `AUTH_MODE=oidc`, analyze requires a JWT bearer token. History and workflow endpoints always require an authenticated principal (`AUTH_MODE=disabled` returns `401`). Workflow proposal/approval routes require `communications:workflow`. Execute requires `communications:send`. Health remains public; readiness remains unauthenticated but probes PostgreSQL when `DATABASE_URL` is set. Production requires both `AUTH_MODE=oidc` and a PostgreSQL `DATABASE_URL`. Live Entra is the first identity provider; ECI remains provider-independent. User identity, runtime AI identity, database identity, and GitHub deploy identity stay separate. Azure real-bearer authorized inference is verified over HTTPS. AWS real-bearer TLS verification is not claimed. When `AI_PROVIDER=mock`, there are no external network calls. When `AI_PROVIDER=microsoft_foundry`, inference goes to Microsoft Foundry using Entra ID. When `AI_PROVIDER=amazon_bedrock`, inference goes to Amazon Bedrock through Converse. Automated tests do not execute those cloud paths. Live ECI → Foundry and ECI → Bedrock workload inference was verified in Phase 6. Phase 8D verified one authorized Foundry call after application-user auth; AWS authorized Bedrock after a real bearer is deferred until TLS. Phase 9 persistence is proven against ephemeral CI PostgreSQL, not against Azure Database for PostgreSQL or Amazon RDS. Current cloud runtimes are not configured with Phase 9 databases and must not receive this image until a colocated database exists. Phase 10 Gmail and Graph adapters are read-only REST clients with in-memory `AccessTokenProvider` injection. They are not production OAuth, not cloud-hosted mailbox onboarding, and not a live mailbox → AI path. Phase 11A adds `WorkflowAction` and capability-specific permissions. Phase 11B persists user-owned workflow actions. Phase 11C exposes proposal and approval HTTP. Phase 11D adds a write execution port, a deterministic fake, and two-transaction execute-after-approval. Phase 12E routes Graph and Gmail writers through `CommunicationActionExecutorFactory` and `POST /api/v1/workflow-actions/{action_id}/execute`. Uncertain provider outcomes remain `EXECUTING` with HTTP 503. Phase 13 adds delegated Gmail and Microsoft Graph OAuth, opaque credential stores (memory, Azure Key Vault, AWS Secrets Manager), PostgreSQL advisory-lock mutation coordination, owned disconnect/reauthorize HTTP, and confirmed permanent refresh failure → `REAUTH_REQUIRED` with a definite no-send `FAILED` workflow outcome. Automatic replies remain later work. User-facing connector message-ingestion HTTP is not implemented.

## Phase 8 identity, deployment, and ingress

```text
APPLICATION USER

    Microsoft Entra ID
            |
          JWT
            |
            v
      ECI REST API
            |
        issuer + subject
            |
      users.id UUID
            |
 CommunicationAnalysisWorkflowService
     /                \
AIProvider        PostgreSQL repositories
 /        \              |
Foundry  Bedrock    analyses owned by user_id
 UAMI    Task Role

DEPLOYMENT

         GitHub Actions
           /          \
        OIDC          OIDC
         |              |
 Azure deploy UAMI   AWS deploy IAM role
         |              |
        ACR            ECR
         |              |
        ACA            ECS

INGRESS

Azure live: HTTPS → Container Apps → ECI
AWS current: operator /32 HTTP → ECS task → ECI (verification-only)
AWS verified, not retained: HTTPS / domain / ACM → ALB → ECS
```

See [`identity.mmd`](../diagrams/identity.mmd), [`mailbox-oauth.mmd`](../diagrams/mailbox-oauth.mmd), [`persistence.mmd`](../diagrams/persistence.mmd), [`persistence-cloud.mmd`](../diagrams/persistence-cloud.mmd), [`cicd.mmd`](../diagrams/cicd.mmd), and [`ingress.mmd`](../diagrams/ingress.mmd).

Three identity domains stay separate:

```text
APPLICATION USER
    Entra/OIDC JWT → AuthenticatedPrincipal → users.id

MAILBOX DELEGATED IDENTITY
    ECI user → Google/Microsoft consent → credential store
    → ConnectorAccount.credential_ref → AccessTokenProvider

CLOUD WORKLOAD IDENTITY
    Azure Container Apps → Managed Identity / DefaultAzureCredential
    AWS ECS → ECS Task Role / boto3 default credential chain
```

PostgreSQL stores the opaque locator and advisory-lock coordination, not OAuth tokens.

## Future Extensibility

Phase 8 identity separation is implemented: application-user OIDC JWT, Azure/AWS workload identity, and GitHub OIDC deploy identities. Phase 9 adds a fourth class: database identity from ECI to PostgreSQL. Phase 7 observability is implemented: portable structured JSON on stdout, `request_id` / `X-Request-ID` correlation, `duration_ms`, and `error_class`. Azure retains logs in Log Analytics and exposes native Container Apps metrics. AWS retains logs in CloudWatch via awslogs and exposes standard ECS CPU/memory metrics. Distributed tracing, custom metrics, dashboards, and alerts remain deferred. Managed cloud PostgreSQL and private DB networking remain later work. Phase 10 connector ingestion is implemented as a domain/application/infrastructure path. Phase 13 implements production mailbox delegated OAuth, disconnect/reauthorize HTTP, Azure Key Vault and AWS Secrets Manager stores, and PostgreSQL advisory-lock coordination. Connector message-ingestion HTTP, synchronization, attachments, and automatic replies remain later work. Environment-backed `CommunicationCredentialResolver` remains the local/dev path for legacy locators. Production mailbox OAuth uses the opaque store. Phase 11A encodes `WorkflowAction` and capability-specific permissions. Phase 11B persists user-owned `workflow_actions` with proposed/approved reply snapshots and no analysis FK. Phase 11C exposes create, list, get, approve, and reject over `/api/v1/workflow-actions`. Phase 11D adds `CommunicationActionExecutor`, `FakeCommunicationActionExecutor`, and `WorkflowActionExecutionService` with a two-transaction boundary. Phase 12E routes Graph and Gmail writers through `CommunicationActionExecutorFactory` and `POST /api/v1/workflow-actions/{action_id}/execute`. Additional AI providers can still be added behind `AIProvider` and the factory without changing the application or API layers. Additional communication vendors can implement `CommunicationConnector` without changing domain analysis models. See [Persistence](persistence.md), [Provider Abstraction](provider-abstraction.md), [Observability](../cloud/observability.md), [Authentication](../cloud/authentication.md), [PostgreSQL strategy](../cloud/persistence.md), [Phase 10](../roadmap/phase-10-communication-connectors.md), [Phase 11](../roadmap/phase-11-workflow-automation.md), and [`docs/cloud/`](../cloud/README.md).
