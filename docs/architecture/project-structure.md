# Project Structure

This reflects the actual repository layout as of Phase 5. Directories with only an empty `__init__.py` or a `.gitkeep` are labeled as scaffolds, not implemented capabilities.

```text
app/
├── api/
│   ├── router.py            # assembles the versioned API router (health + communications)
│   ├── dependencies.py       # FastAPI dependency providers (AIProvider, CommunicationAnalysisService)
│   └── routes/
│       ├── health.py         # GET /health, GET /api/v1/health, GET /api/v1/readiness
│       └── communications.py # POST /api/v1/communications/analyze
├── application/
│   ├── exceptions.py         # AnalysisFailedError
│   └── services/
│       └── communication_analysis.py  # CommunicationAnalysisService
├── core/
│   ├── config.py             # Settings (Pydantic Settings) and get_settings()
│   ├── logging.py            # structlog configuration, get_logger()
│   ├── exceptions.py          # ContextMeshError, ConfigurationError, ServiceUnavailableError
│   └── security.py           # empty scaffold — no implementation
├── domain/
│   ├── enums.py               # SourceType, PriorityLevel, MessageCategory
│   ├── models/
│   │   ├── message.py         # CommunicationMessage, MessageMetadata
│   │   ├── analysis.py        # Summary, Priority, ActionItem, DraftReply, CommunicationAnalysis
│   │   └── validation.py      # shared field-validation helper
│   ├── schemas/
│   │   └── analysis.py        # CommunicationRequest, CommunicationAnalysisResult
│   ├── interfaces/
│   │   └── ai_provider.py     # AIProvider abstract interface
│   └── services/              # empty scaffold package — unused (business logic lives in app/application)
├── providers/
│   ├── factory.py             # create_ai_provider(): configuration-driven AIProvider selection
│   ├── mock/
│   │   └── provider.py        # MockAIProvider — the only implemented provider
│   ├── aws/                    # empty scaffold package — no Amazon Bedrock code
│   └── azure/                  # empty scaffold package — no Azure AI Foundry code
├── infrastructure/
│   ├── monitoring/             # empty scaffold package — no implementation
│   ├── parsers/                # empty scaffold package — no implementation
│   └── storage/                # empty scaffold package — no implementation
├── schemas/
│   ├── health.py               # LivenessResponse, HealthResponse, ReadinessResponse
│   └── errors.py                # ErrorResponse (OpenAPI documentation only)
├── utils/                       # empty scaffold package — no implementation
└── main.py                      # FastAPI app factory, lifespan, exception handlers

tests/
├── conftest.py
├── unit/
│   ├── domain/                  # enums, models, schemas, interface conformance
│   ├── providers/                # MockAIProvider, provider factory
│   ├── application/               # CommunicationAnalysisService
│   ├── test_config.py
│   ├── test_logging.py
│   ├── test_exceptions.py
│   └── test_dependencies.py
└── integration/
    ├── test_health.py
    ├── test_communications.py
    └── test_docs.py             # OpenAPI schema assertions

docs/
├── roadmap/                     # phase-by-phase roadmap (curated separately; not modified by this pass)
├── api/                          # this documentation set
├── architecture/                 # this documentation set
├── decisions/                     # Architecture Decision Records
├── diagrams/                      # Mermaid diagram sources
└── cloud/                         # placeholder — future Azure/AWS/deployment docs

deployment/
├── docker/                       # placeholder (.gitkeep only)
├── azure/                        # placeholder (.gitkeep only)
└── aws/                          # placeholder (.gitkeep only)
```

## Role of Each Top-Level Package

- **`app/api`** — HTTP transport layer. Owns FastAPI routers, request/response wiring, and dependency injection. No business logic.
- **`app/application`** — Use-case orchestration. Currently one service, `CommunicationAnalysisService`, coordinating providers and translating failures.
- **`app/core`** — Cross-cutting infrastructure shared by every layer: configuration, structured logging, and the base exception hierarchy. `security.py` is reserved for future authentication/authorization work and is currently empty.
- **`app/domain`** — Provider-independent business vocabulary: enums, models, schemas, and the `AIProvider` interface. No framework or cloud dependencies. `app/domain/services/` is an empty scaffold; no domain-layer services have been needed so far — orchestration lives in `app/application`.
- **`app/providers`** — Concrete `AIProvider` implementations plus the selection factory. Only `mock` is implemented; `aws` and `azure` are empty scaffolds reserved for future work.
- **`app/infrastructure`** — Reserved for future cross-cutting infrastructure concerns (monitoring, parsing, storage). All three subpackages are currently empty scaffolds with no implementation or usage anywhere in the codebase.
- **`app/schemas`** — Transport-only Pydantic response models for endpoints that don't map to a domain concept (health, readiness, generic error responses). Kept separate from `app/domain/schemas`, which holds business-meaningful request/response schemas.
- **`app/utils`** — Empty scaffold package; no shared utility functions have been introduced yet.
- **`tests`** — Mirrors the `app` structure for unit tests (`tests/unit`) and adds black-box HTTP tests (`tests/integration`) using FastAPI's `TestClient`. All 94 tests run offline with no external credentials.
- **`docs`** — Project documentation, split by concern (API, architecture, decisions, diagrams, roadmap) plus a placeholder `cloud/` section for not-yet-implemented cloud provider and deployment documentation.
- **`deployment`** — Currently placeholder directories only (`.gitkeep` files for `docker/`, `azure/`, `aws/`); no Dockerfile content, Compose configuration, or deployment manifests are implemented yet (the root `Dockerfile` and `docker-compose.yml` are also present but empty).

## Directories Not Listed Above

`data/`, `scripts/`, `.github/`, and root files such as `LICENSE`, `Dockerfile`, and `docker-compose.yml` exist in the repository but contain no implementation relevant to Phase 5 and are out of scope for this documentation pass.
