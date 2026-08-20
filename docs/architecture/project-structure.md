# Project Structure

This reflects the actual repository layout as of Phase 9. Directories with only an empty `__init__.py` or a `.gitkeep` are labeled as scaffolds, not implemented capabilities.

```text
app/
├── api/
│   ├── router.py            # assembles the versioned API router (health + communications + analyses)
│   ├── dependencies.py       # FastAPI dependency providers (AI, workflow, identity, history)
│   └── routes/
│       ├── health.py         # GET /health, GET /api/v1/health, GET /api/v1/readiness
│       ├── communications.py # POST /api/v1/communications/analyze
│       └── analyses.py       # GET/DELETE /api/v1/analyses
├── application/
│   ├── exceptions.py         # AnalysisFailedError, AnalysisNotFoundError
│   └── services/
│       ├── communication_analysis.py  # CommunicationAnalysisService (AI-only)
│       ├── communication_analysis_workflow.py  # persist-after-analyze workflow
│       ├── identity.py       # IdentityResolver
│       └── analysis_history.py  # AnalysisHistoryService
├── core/
│   ├── config.py             # Settings (Pydantic Settings) and get_settings()
│   ├── logging.py            # structlog configuration, get_logger()
│   ├── exceptions.py          # ECIPlatformError, ConfigurationError, ServiceUnavailableError, PersistenceError
│   └── security.py           # OIDC JWT validation and AuthenticatedPrincipal
├── domain/
│   ├── enums.py               # SourceType, PriorityLevel, MessageCategory
│   ├── models/
│   │   ├── message.py         # CommunicationMessage, MessageMetadata
│   │   ├── analysis.py        # Summary, Priority, ActionItem, DraftReply, CommunicationAnalysis
│   │   └── validation.py      # shared field-validation helper
│   ├── schemas/
│   │   └── analysis.py        # CommunicationRequest, CommunicationAnalysisResult
│   ├── interfaces/
│   │   ├── ai_provider.py     # AIProvider abstract interface
│   │   ├── identity_repository.py
│   │   ├── analysis_repository.py
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
│   ├── monitoring/             # empty scaffold package — no implementation
│   ├── parsers/                # empty scaffold package — no implementation
│   └── storage/                # SQLAlchemy runtime, models, UoW, repositories
│       ├── models.py
│       ├── database.py
│       ├── unit_of_work.py
│       ├── runtime.py
│       ├── migration_config.py
│       └── repositories/
├── schemas/
│   ├── health.py               # LivenessResponse, HealthResponse, ReadinessResponse
│   ├── analysis.py             # CommunicationAnalysisResponse, history items
│   └── errors.py                # ErrorResponse (OpenAPI documentation only)
├── utils/                       # empty scaffold package — no implementation
└── main.py                      # FastAPI app factory, lifespan, exception handlers

tests/
├── conftest.py
├── unit/
│   ├── domain/
│   ├── providers/
│   ├── application/
│   └── ...
├── integration/
│   ├── test_health.py
│   ├── test_communications.py
│   └── test_docs.py
└── postgres/                    # skipped locally unless ECI_POSTGRES_TEST_DATABASE_URL is set

alembic/
└── versions/                    # revision 9a0001

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

- **`app/api`** — HTTP transport layer. Owns FastAPI routers, request/response wiring, and dependency injection. No business logic. Never imports a concrete provider class.
- **`app/application`** — Use-case orchestration. `CommunicationAnalysisService` coordinates AI providers. Workflow, identity, and history services add user-owned persistence around that AI path.
- **`app/core`** — Cross-cutting infrastructure shared by every layer: configuration, structured logging, JWT bearer validation, and the base exception hierarchy.
- **`app/domain`** — Provider-independent business vocabulary: enums, models, schemas, `AIProvider`, and persistence repository/UoW interfaces. No framework, SQLAlchemy, or cloud dependencies.
- **`app/providers`** — Concrete `AIProvider` implementations plus the selection factory. `mock`, `microsoft_foundry`, and `amazon_bedrock` are implemented. `common/` holds the shared LLM analysis contract used by the two real adapters. `aws/` and `azure/` remain unused Phase 3 vendor scaffolds; they are not active provider implementations and were not used for Bedrock.
- **`app/infrastructure`** — Persistence runtime lives in `storage/`. `monitoring/` and `parsers/` remain empty scaffolds.
- **`app/schemas`** — Transport-only Pydantic response models for endpoints that don't map solely to a domain concept (health, readiness, analyze `analysis_id`, history items, generic error responses). Kept separate from `app/domain/schemas`, which holds business-meaningful request/response schemas.
- **`app/utils`** — Empty scaffold package; no shared utility functions have been introduced yet.
- **`tests`** — Mirrors the `app` structure for unit tests (`tests/unit`) and adds black-box HTTP tests (`tests/integration`) using FastAPI's `TestClient`. PostgreSQL dialect tests live in `tests/postgres/` and skip unless an explicit test URL is set. Default local tests run offline with no Docker, Azure, or AWS.
- **`docs`** — Project documentation, split by concern (API, architecture, decisions, diagrams, roadmap, cloud).
- **`deployment`** — Azure and AWS operator runbooks. The provider-independent `Dockerfile`, `docker-compose.yml`, and `.dockerignore` live at the repository root. `deployment/docker/` remains a `.gitkeep` placeholder.

## Directories Not Listed Above

`data/`, `scripts/`, `.github/`, and root files such as `LICENSE`, `Dockerfile`, and `docker-compose.yml` exist in the repository. The root Docker files are the Phase 6C image foundation.
