# Clean Architecture in ECI Platform

ECI Platform applies clean-architecture-style layering: dependency direction points inward, toward stable, framework-independent code, and outward layers own the framework and infrastructure details.

## Dependency Direction

```text
API  →  Application  →  Domain  ←  Providers
                          ↑
                        Core
                          ↑
                   Infrastructure
                   (storage implements persistence ports;
                    communication connectors implement
                    CommunicationConnector;
                    credentials implement
                    CommunicationCredentialResolver;
                    executors implement
                    CommunicationActionExecutor)
```

- `app/api` depends on `app/application` (indirectly, via dependencies) and on `app/domain` schemas.
- `app/application` depends on `app/domain` (models, schemas, AI, connector, executor, and persistence interfaces) and `app/core` (logging, exceptions).
- `app/providers` depends on `app/domain` (implements `AIProvider`, uses domain models/schemas) and `app/core` (config, exceptions).
- `app/infrastructure/storage` depends on `app/domain` persistence interfaces and `app/core`. It contains SQLAlchemy and Alembic-facing runtime types.
- `app/infrastructure/connectors` depends on `app/domain` (`CommunicationConnector`) and `app/core` (connector-neutral exceptions). It contains Gmail REST, Microsoft Graph REST, and fake adapters. It does not import API, SQLAlchemy ORM, or `AIProvider`.
- `app/infrastructure/executors` depends on `app/domain` (`CommunicationActionExecutor`) and `app/core` (execution and unavailability errors). It implements a deterministic fake, a Microsoft Graph `/reply` adapter, and a Gmail metadata-plus-send adapter. It does not import API, SQLAlchemy, connector adapters, or `AIProvider`.
- `app/infrastructure/credentials` depends on `app/domain` (`CommunicationCredentialResolver`, `CommunicationCredentialStore`) and `app/core` (credential-neutral exceptions and logging). Environment lookup, the in-memory store, locator issuance, and the refreshable resolver stay free of cloud SDKs. Azure Key Vault and AWS Secrets Manager stores live in dedicated modules and are selected by `CREDENTIAL_STORE_BACKEND`. Gmail/Graph adapters and OAuth routes do not import those SDKs.
- `app/domain` depends on nothing else in the application — it is the innermost, most stable layer. Persistence, connector, executor, and credential-resolver contracts live there as interfaces, not as ORM models or vendor SDKs.

This matches the direction required by `.cursor/rules/enterprise-communication-intelligence.mdc`: domain code must remain independent of FastAPI, Azure SDKs, and AWS SDKs.

## Stable Inner Layers

`app/domain` is the most stable part of the codebase:

- It defines enums, Pydantic models (including `WorkflowAction`), schemas, the `AIProvider` interface, the `CommunicationConnector` contract, the `CommunicationActionExecutor` write port, and the `CommunicationCredentialResolver` credential port.
- It imports only Pydantic and the Python standard library — never `fastapi`, `httpx` (as an HTTP client), or any cloud SDK.
- Nothing in `app/domain` changes when a new provider, route, or deployment target is added.

## Infrastructure at the Edges

Framework and infrastructure concerns live at the outer edges:

- **FastAPI** is confined to `app/api` (routes, dependency wiring, router assembly) and `app/main.py` (application construction, lifespan, exception handlers).
- **Provider-specific code** is confined to `app/providers/<provider_name>/`. `app/providers/mock/`, `app/providers/microsoft_foundry/`, and `app/providers/amazon_bedrock/` are implemented. Shared LLM analysis mechanics live in `app/providers/common/`.
- **SQLAlchemy and Alembic** are confined to `app/infrastructure/storage/` and `alembic/`. Application services depend on repository interfaces.
- **Communication connector adapters** are confined to `app/infrastructure/connectors/`. Application ingestion depends on `CommunicationConnector`, not Gmail or Graph types. Production read routing uses `CommunicationConnectorFactory`; the infrastructure factory selects Gmail or Graph from an owned account without invoking tokens or mailbox HTTP.
- **Action executor adapters** are confined to `app/infrastructure/executors/`. Application execution depends on `CommunicationActionExecutorFactory`, not a concrete fake, Graph, or Gmail class. The production factory selects Graph or Gmail from an owned account.
- **Mailbox credential resolution** is confined to `app/infrastructure/credentials/`. The production factory calls the resolver to obtain an `AccessTokenProvider`; the application execution service does not import the resolver or invoke tokens. Mailbox tokens are not loaded into `Settings`. Phase 13B keeps environment-backed execute as the runtime default and adds an explicit construction hook for the refreshable resolver.
- **Configuration and logging setup** (`app/core/config.py`, `app/core/logging.py`) are the only places application Settings and structlog configuration are touched. Mailbox credential environment variables are looked up individually by the environment-backed resolver when resolution is requested; they are not Settings fields.

## Why Domain Code Is Independent of FastAPI and Cloud SDKs

- **Testability:** `app/domain` and `app/application` are tested with plain Python objects (see `tests/unit/domain`, `tests/unit/application`) — no FastAPI `TestClient` or cloud credentials required.
- **Provider replaceability:** Because `CommunicationAnalysisService` only knows about `AIProvider`, Microsoft Foundry and Amazon Bedrock were added without modifying application or domain code — only `app/providers/factory.py` gained new branches.
- **Connector replaceability:** Because `CommunicationIngestionService` only knows about `CommunicationConnector`, Gmail and Microsoft Graph adapters were added in infrastructure without changing the domain analysis models or `AIProvider`. Vendor JSON/MIME stays inside the adapter. Phase 14B adds `CommunicationConnectorFactory` so application code can obtain a connector from an owned account without importing Gmail or Graph classes.
- **Executor replaceability:** Because `WorkflowActionExecutionService` only knows about `CommunicationActionExecutorFactory`, Graph and Gmail writers are selected from an owned account without changing proposal/approval HTTP or `CommunicationConnector`.
- **Credential replaceability:** Because write adapters depend on `CommunicationCredentialResolver` rather than `os.environ` or a cloud secret SDK, the environment-backed local resolver and the refreshable resolver share the same port. Key Vault and Secrets Manager are `CommunicationCredentialStore` implementations behind that port.
- **Avoiding lock-in:** Domain models (`CommunicationMessage`, `CommunicationAnalysis`, etc.) do not encode any vendor-specific concepts, keeping the business vocabulary reusable across future channels (Slack, Teams, WhatsApp, etc. — represented today as `SourceType` enum values; email adapters exist for Gmail and Microsoft Graph).

## Trade-offs (Current State)

- **Not full DDD:** ECI Platform borrows clean architecture's *layering and dependency direction*, but does not implement full Domain-Driven Design — there are no aggregates, domain events, or a ubiquitous-language modeling process. Phase 9 adds repository and unit-of-work interfaces for persistence. Phase 10 adds `CommunicationConnector` as another inverted port. Phase 11A adds `WorkflowAction` and an explicit domain state machine. Phase 11D adds `CommunicationActionExecutor` as a write port separate from the read connector.
- **Application services remain few and focused:** `CommunicationAnalysisService` stays AI-only. `CommunicationAnalysisWorkflowService` orchestrates persist-after-analyze; it is not the Phase 11 business-workflow service. Ingestion and connector-account services orchestrate connector fetch and account lifecycle. `WorkflowActionService` remains proposal/approval lifecycle. `WorkflowActionExecutionService` orchestrates execute-after-approval. No generic use-case base class or command/query separation has been introduced.
- **Framework coupling still exists at the edges by design:** `app/api` necessarily depends on FastAPI (`Depends`, `APIRouter`), `app/providers/microsoft_foundry` depends on Azure SDKs, `app/providers/amazon_bedrock` depends on boto3, `app/infrastructure/storage` depends on SQLAlchemy, and `app/infrastructure/connectors` depends on `httpx`. This is intentional — clean architecture pushes volatility to the edges rather than eliminating it.
- **Core is shared, not layered further:** `app/core` (config, logging, exceptions, security) is used by every layer. It is deliberately minimal and framework-agnostic (aside from being read by FastAPI's lifespan hook in `app/main.py`), rather than being split into its own strict sub-layers.
- **Outer implementations are not storage-only:** persistence adapters live in `app/infrastructure/storage`, AI provider adapters in `app/providers`, communication connector adapters in `app/infrastructure/connectors`, mailbox credential resolution in `app/infrastructure/credentials`, and write adapters in `app/infrastructure/executors`. Outer layers implement ports defined inward.
