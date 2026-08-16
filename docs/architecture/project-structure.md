# Project Structure

This reflects the actual repository layout as of Phase 6B. Directories with only an empty `__init__.py` or a `.gitkeep` are labeled as scaffolds, not implemented capabilities.

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
│   ├── exceptions.py          # ECIPlatformError, ConfigurationError, ServiceUnavailableError
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
│   ├── providers/                # Mock, Foundry, Bedrock, common layer, factory
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
├── roadmap/                     # phase-by-phase roadmap
├── api/                          # REST API documentation
├── architecture/                 # architecture documentation
├── decisions/                     # Architecture Decision Records
├── diagrams/                      # Mermaid diagram sources
└── cloud/                         # Microsoft Foundry, Amazon Bedrock, and future hosting docs

deployment/
├── docker/                       # placeholder (.gitkeep only)
├── azure/                        # placeholder (.gitkeep only)
└── aws/                          # placeholder (.gitkeep only)
```

## Role of Each Top-Level Package

- **`app/api`** — HTTP transport layer. Owns FastAPI routers, request/response wiring, and dependency injection. No business logic. Never imports a concrete provider class.
- **`app/application`** — Use-case orchestration. Currently one service, `CommunicationAnalysisService`, coordinating providers and translating failures.
- **`app/core`** — Cross-cutting infrastructure shared by every layer: configuration, structured logging, and the base exception hierarchy. `security.py` is reserved for future authentication/authorization work and is currently empty.
- **`app/domain`** — Provider-independent business vocabulary: enums, models, schemas, and the `AIProvider` interface. No framework or cloud dependencies. `app/domain/services/` is an empty scaffold; no domain-layer services have been needed so far — orchestration lives in `app/application`.
- **`app/providers`** — Concrete `AIProvider` implementations plus the selection factory. `mock`, `microsoft_foundry`, and `amazon_bedrock` are implemented. `common/` holds the shared LLM analysis contract used by the two real adapters. `aws/` and `azure/` remain unused Phase 3 vendor scaffolds; they are not active provider implementations and were not used for Bedrock.
- **`app/infrastructure`** — Reserved for future cross-cutting infrastructure concerns (monitoring, parsing, storage). All three subpackages are currently empty scaffolds with no implementation or usage anywhere in the codebase.
- **`app/schemas`** — Transport-only Pydantic response models for endpoints that don't map to a domain concept (health, readiness, generic error responses). Kept separate from `app/domain/schemas`, which holds business-meaningful request/response schemas.
- **`app/utils`** — Empty scaffold package; no shared utility functions have been introduced yet.
- **`tests`** — Mirrors the `app` structure for unit tests (`tests/unit`) and adds black-box HTTP tests (`tests/integration`) using FastAPI's `TestClient`. All tests run offline with no external credentials.
- **`docs`** — Project documentation, split by concern (API, architecture, decisions, diagrams, roadmap, cloud).
- **`deployment`** — Currently placeholder directories only (`.gitkeep` files for `docker/`, `azure/`, `aws/`); no Dockerfile content, Compose configuration, or deployment manifests are implemented yet.

## Directories Not Listed Above

`data/`, `scripts/`, `.github/`, and root files such as `LICENSE`, `Dockerfile`, and `docker-compose.yml` exist in the repository but contain no implementation relevant to Phase 6B and are out of scope for this documentation pass.
