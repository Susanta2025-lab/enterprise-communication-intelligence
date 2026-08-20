# Architecture Overview

## Implemented Request Path

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

`CommunicationAnalysisService` remains AI-only. Persistence is optional in development when `DATABASE_URL` is omitted. Every layer is exercised by tests spanning `tests/unit`, `tests/integration`, and GitHub `tests/postgres`. Automated tests stay offline; Microsoft Foundry and Amazon Bedrock are exercised through mocked SDK clients. Live ECI → Bedrock verification is complete. PostgreSQL dialect coverage is proven in CI, not against a managed cloud database.

## Purpose of Each Layer

- **FastAPI REST API (`app/api`)** — HTTP transport. Defines routes (`app/api/routes/`), the API router assembly (`app/api/router.py`), and dependency wiring (`app/api/dependencies.py`). Contains no business logic; every route validates input via Pydantic and delegates to a service.
- **Application service (`app/application`)** — Orchestrates use cases. `CommunicationAnalysisService` remains AI-only. `CommunicationAnalysisWorkflowService` resolves internal user ownership, calls the AI service, then persists through `AnalysisHistoryService`. Application code depends on domain repository/UoW interfaces, not SQLAlchemy.
- **Domain (`app/domain`)** — Provider-independent business objects: enums (`SourceType`, `PriorityLevel`, `MessageCategory`), models (`CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`), schemas (`CommunicationRequest`, `CommunicationAnalysisResult`), the `AIProvider` interface, and persistence repository/UoW interfaces. Domain code imports neither FastAPI, SQLAlchemy, nor any cloud SDK.
- **Providers (`app/providers`)** — Concrete implementations of `AIProvider`. `MockAIProvider`, `MicrosoftFoundryProvider`, and `AmazonBedrockProvider` are implemented. The two real LLM adapters share `app/providers/common/`. `app/providers/factory.py` selects a provider from configuration.
- **Core (`app/core`)** — Cross-cutting concerns: `config.py` (Pydantic Settings, including `DATABASE_URL`), `logging.py` (structlog configuration), `telemetry.py` (request-safe `duration_ms` and `error_class` helpers), `exceptions.py` (the base application exception hierarchy, including `PersistenceError`), `security.py` (OIDC JWT validation and `AuthenticatedPrincipal`). HTTP `request_id` binding lives in `app/api/middleware.py`.
- **Infrastructure storage (`app/infrastructure/storage`)** — SQLAlchemy models, engine, unit of work, and repository implementations. Domain and application code do not import these types except through API dependency wiring.

## Provider Independence

The application service and every layer above it depend only on `app.domain.interfaces.AIProvider`, never on `MockAIProvider`, `MicrosoftFoundryProvider`, `AmazonBedrockProvider`, or any other concrete provider class. Provider selection happens in exactly one place — `app/providers/factory.py` — driven by the `AI_PROVIDER` setting. This means:

- Swapping providers requires no change to `CommunicationAnalysisService` or any route.
- Amazon Bedrock was added as `app/providers/amazon_bedrock/` plus one factory branch, without changing application or API code.

## Current Implementation Boundary

The system is fully synchronous. Through Phase 8 the runtime was stateless with respect to application data. Phase 9 adds optional persistence when `DATABASE_URL` is configured; omitting it keeps analyze-only behavior. When `AUTH_MODE=oidc`, analyze requires a JWT bearer token. History endpoints always require an authenticated principal (`AUTH_MODE=disabled` returns `401`). Health remains public; readiness remains unauthenticated but probes PostgreSQL when `DATABASE_URL` is set. Production requires both `AUTH_MODE=oidc` and a PostgreSQL `DATABASE_URL`. Live Entra is the first identity provider; ECI remains provider-independent. User identity, runtime AI identity, database identity, and GitHub deploy identity stay separate. Azure real-bearer authorized inference is verified over HTTPS. AWS real-bearer TLS verification is not claimed. When `AI_PROVIDER=mock`, there are no external network calls. When `AI_PROVIDER=microsoft_foundry`, inference goes to Microsoft Foundry using Entra ID. When `AI_PROVIDER=amazon_bedrock`, inference goes to Amazon Bedrock through Converse. Automated tests do not execute those cloud paths. Live ECI → Foundry and ECI → Bedrock workload inference was verified in Phase 6. Phase 8D verified one authorized Foundry call after application-user auth; AWS authorized Bedrock after a real bearer is deferred until TLS. Phase 9 persistence is proven against ephemeral CI PostgreSQL, not against Azure Database for PostgreSQL or Amazon RDS. Current cloud runtimes are not configured with Phase 9 databases and must not receive this image until a colocated database exists.

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

See [`identity.mmd`](../diagrams/identity.mmd), [`persistence.mmd`](../diagrams/persistence.mmd), [`persistence-cloud.mmd`](../diagrams/persistence-cloud.mmd), [`cicd.mmd`](../diagrams/cicd.mmd), and [`ingress.mmd`](../diagrams/ingress.mmd).

## Future Extensibility

Phase 8 identity separation is implemented: application-user OIDC JWT, Azure/AWS workload identity, and GitHub OIDC deploy identities. Phase 9 adds a fourth class: database identity from ECI to PostgreSQL. Phase 7 observability is implemented: portable structured JSON on stdout, `request_id` / `X-Request-ID` correlation, `duration_ms`, and `error_class`. Azure retains logs in Log Analytics and exposes native Container Apps metrics. AWS retains logs in CloudWatch via awslogs and exposes standard ECS CPU/memory metrics. Distributed tracing, custom metrics, dashboards, and alerts remain deferred. Managed cloud PostgreSQL, private DB networking, and connector ingestion remain later work. Additional providers can still be added behind `AIProvider` and the factory without changing the application or API layers. See [Persistence](persistence.md), [Provider Abstraction](provider-abstraction.md), [Observability](../cloud/observability.md), [Authentication](../cloud/authentication.md), [PostgreSQL strategy](../cloud/persistence.md), and [`docs/cloud/`](../cloud/README.md).
