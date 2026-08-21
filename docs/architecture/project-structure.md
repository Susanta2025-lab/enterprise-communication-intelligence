# Project Structure

This reflects the actual repository layout as of Phase 11C. Directories with only an empty `__init__.py` or a `.gitkeep` are labeled as scaffolds, not implemented capabilities.

```text
app/
├── api/
│   ├── router.py            # assembles the versioned API router (health + communications + analyses + workflow-actions)
│   ├── dependencies.py       # FastAPI dependency providers (AI, workflow, identity, history, require_permission)
│   └── routes/
│       ├── health.py         # GET /health, GET /api/v1/health, GET /api/v1/readiness
│       ├── communications.py # POST /api/v1/communications/analyze
│       ├── analyses.py       # GET/DELETE /api/v1/analyses
│       └── workflow_actions.py  # POST/GET workflow-actions; POST approve/reject
├── application/
│   ├── exceptions.py         # AnalysisFailedError, AnalysisNotFoundError, connector-account and workflow-action errors
│   └── services/
│       ├── communication_analysis.py  # CommunicationAnalysisService (AI-only)
│       ├── communication_analysis_workflow.py  # persist-after-analyze workflow
│       ├── communication_ingestion.py  # CommunicationIngestionService
│       ├── connector_accounts.py  # ConnectorAccountService
│       ├── workflow_actions.py  # WorkflowActionService (create/get/list/approve/reject)
│       ├── identity.py       # IdentityResolver
│       └── analysis_history.py  # AnalysisHistoryService
├── core/
│   ├── config.py             # Settings (Pydantic Settings) and get_settings()
│   ├── logging.py            # structlog configuration, get_logger()
│   ├── exceptions.py          # ECIPlatformError, ConfigurationError, ServiceUnavailableError, PersistenceError, connector-neutral errors
│   └── security.py           # OIDC JWT validation, AuthenticatedPrincipal, capability-specific authorize()
├── domain/
│   ├── enums.py               # SourceType, PriorityLevel, MessageCategory, ConnectorAccountStatus, WorkflowActionType, WorkflowActionStatus
│   ├── exceptions.py          # InvalidWorkflowTransitionError
│   ├── models/
│   │   ├── message.py         # CommunicationMessage, MessageMetadata
│   │   ├── analysis.py        # Summary, Priority, ActionItem, DraftReply, CommunicationAnalysis
│   │   ├── workflow.py        # WorkflowAction (approval-gated; not ActionItem)
│   │   └── validation.py      # shared field-validation helper
│   ├── schemas/
│   │   └── analysis.py        # CommunicationRequest, CommunicationAnalysisResult
│   ├── interfaces/
│   │   ├── ai_provider.py     # AIProvider abstract interface
│   │   ├── communication_connector.py  # CommunicationConnector, ConnectorMessageQuery, MessagePage
│   │   ├── connector_account_repository.py
│   │   ├── identity_repository.py
│   │   ├── analysis_repository.py
│   │   ├── workflow_action_repository.py
│   │   └── persistence_unit_of_work.py
│   └── services/              # empty scaffold package — unused (business logic lives in app/application)
├── providers/
│   ├── factory.py             # create_ai_provider(): configuration-driven AIProvider selection
│   ├── common/
│   │   ├── output.py          # shared LLM analysis models, parse, and domain mapping
│   │   └── prompts.py         # shared ECI system/user prompt construction
│   ├── mock/
│   │   └── provider.py        # MockAIProvider
│   ├── microsoft_foundry/
│   │   ├── provider.py        # MicrosoftFoundryProvider
│   │   └── output.py          # OpenAI-strict JSON Schema transformation
│   ├── amazon_bedrock/
│   │   ├── provider.py        # AmazonBedrockProvider
│   │   └── output.py          # Converse schema string and response extraction
│   ├── aws/                   # unused Phase 3 vendor scaffold — not an active provider
│   └── azure/                 # unused Phase 3 vendor scaffold — not an active provider
├── infrastructure/
│   ├── connectors/
│   │   ├── common/
│   │   │   ├── auth.py        # AccessTokenProvider callable; in-memory token injection, not credential_ref resolution
│   │   │   └── html_text.py   # stdlib HTML → plain text
│   │   ├── fake/
│   │   │   └── connector.py   # FakeCommunicationConnector
│   │   ├── gmail/
│   │   │   ├── connector.py   # GmailCommunicationConnector (REST v1)
│   │   │   └── normalization.py
│   │   └── microsoft_graph/
│   │       ├── connector.py   # MicrosoftGraphCommunicationConnector (REST v1.0)
│   │       └── normalization.py
│   ├── monitoring/             # empty scaffold package — no implementation
│   ├── parsers/                # empty scaffold package — no implementation
│   └── storage/                # SQLAlchemy runtime, models, UoW, repositories
│       ├── models.py           # users, external_identities, analyses, connector_accounts, workflow_actions
│       ├── database.py
│       ├── unit_of_work.py
│       ├── runtime.py
│       ├── migration_config.py
│       └── repositories/
│           ├── identity.py
│           ├── analysis.py
│           ├── connector_account.py
│           └── workflow_action.py
├── schemas/
│   ├── health.py               # LivenessResponse, HealthResponse, ReadinessResponse
│   ├── analysis.py             # CommunicationAnalysisResponse, history items
│   ├── workflow.py             # WorkflowActionCreateRequest, WorkflowActionResponse, list wrapper
│   └── errors.py                # ErrorResponse (OpenAPI documentation only)
├── utils/                       # empty scaffold package — no implementation
└── main.py                      # FastAPI app factory, lifespan, exception handlers

tests/
├── conftest.py
├── unit/
│   ├── domain/
│   ├── providers/
│   ├── application/
│   ├── infrastructure/
│   │   ├── connectors/
│   │   └── storage/
│   └── ...
├── integration/
│   ├── test_health.py
│   ├── test_communications.py
│   ├── test_analyses.py
│   ├── test_workflow_actions.py
│   ├── test_docs.py
│   ├── test_ingestion_boundary.py
│   ├── test_gmail_ingestion_boundary.py
│   └── test_microsoft_graph_ingestion_boundary.py
└── postgres/                    # skipped locally unless ECI_POSTGRES_TEST_DATABASE_URL is set

alembic/
└── versions/                    # 9a0001, 10b0001, 11b0001

docs/
├── roadmap/                     # phase-by-phase roadmap
├── api/                          # REST API documentation
├── architecture/                 # architecture documentation
├── decisions/                     # Architecture Decision Records
├── diagrams/                      # Mermaid diagram sources
└── cloud/                         # Microsoft Foundry, Amazon Bedrock, and deployment docs

deployment/
├── docker/                       # placeholder (.gitkeep only; image lives at repo root)
├── azure/                        # Azure Container Apps runbook
└── aws/                          # ECS Fargate runbook
```

## Role of Each Top-Level Package

- **`app/api`** — HTTP transport layer. Owns FastAPI routers, request/response wiring, and dependency injection. No business logic. Never imports a concrete AI provider class or a concrete communication connector. Phase 10 added no connector routes. Phase 11C adds `app/api/routes/workflow_actions.py` over `WorkflowActionService`. Analyze/history keep `communications:analyze`; workflow routes require `communications:workflow` and a real principal.
- **`app/application`** — Use-case orchestration. `CommunicationAnalysisService` coordinates AI providers. Workflow, identity, and history services add user-owned persistence around that AI path. `CommunicationIngestionService` fetches a normalized message through `CommunicationConnector` and reuses the existing workflow. `ConnectorAccountService` manages user-owned connector accounts. `WorkflowActionService` creates, lists, retrieves, approves, and rejects durable workflow actions. `CommunicationAnalysisWorkflowService` is persist-after-analyze orchestration; it is not the Phase 11 `WorkflowAction` service.
- **`app/core`** — Cross-cutting infrastructure shared by every layer: configuration, structured logging, JWT bearer validation, and the base exception hierarchy, including connector-neutral errors.
- **`app/domain`** — Provider-independent business vocabulary: enums, models (including `WorkflowAction`), schemas, `AIProvider`, `CommunicationConnector`, and persistence repository/UoW interfaces. No framework, SQLAlchemy, or cloud dependencies.
- **`app/providers`** — Concrete `AIProvider` implementations plus the selection factory. `mock`, `microsoft_foundry`, and `amazon_bedrock` are implemented. `common/` holds the shared LLM analysis contract used by the two real adapters. `aws/` and `azure/` remain unused Phase 3 vendor scaffolds; they are not active provider implementations and were not used for Bedrock. Communication connectors do not live here.
- **`app/infrastructure`** — Persistence runtime lives in `storage/`. Communication connector adapters live in `connectors/` (`fake`, `gmail`, `microsoft_graph`, plus `common` token/HTML helpers). `monitoring/` and `parsers/` remain empty scaffolds.
- **`app/schemas`** — Transport-only Pydantic response models for endpoints that don't map solely to a domain concept (health, readiness, analyze `analysis_id`, history items, workflow actions, generic error responses). Kept separate from `app/domain/schemas`, which holds business-meaningful request/response schemas.
- **`app/utils`** — Empty scaffold package; no shared utility functions have been introduced yet.
- **`tests`** — Mirrors the `app` structure for unit tests (`tests/unit`) and adds black-box HTTP tests (`tests/integration`) using FastAPI's `TestClient`. Connector ingestion-boundary tests live under `tests/integration/`. PostgreSQL dialect tests live in `tests/postgres/` and skip unless an explicit test URL is set. Default local tests run offline with no Docker, Azure, AWS, Gmail, or Microsoft Graph network calls.
- **`docs`** — Project documentation, split by concern (API, architecture, decisions, diagrams, roadmap, cloud).
- **`deployment`** — Azure and AWS operator runbooks. The provider-independent `Dockerfile`, `docker-compose.yml`, and `.dockerignore` live at the repository root. `deployment/docker/` remains a `.gitkeep` placeholder.

## Directories Not Listed Above

`data/`, `scripts/`, `.github/`, and root files such as `LICENSE`, `Dockerfile`, and `docker-compose.yml` exist in the repository. The root Docker files are the Phase 6C image foundation.
