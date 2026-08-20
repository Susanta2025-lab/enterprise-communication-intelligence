# Dependency Flow

This documents the *actual* import relationships enforced in the current codebase, not aspirational ones.

## Dependency Matrix

| From ↓ / To → | API | Application | Domain | Providers | Core | Infrastructure |
|---|---|---|---|---|---|---|
| **API** (`app/api`) | — | ✅ workflow, identity, history, AI service types | ✅ schemas and records | ✅ only the factory (`create_ai_provider`), never a concrete provider class | ✅ `get_settings`, security, exceptions | ✅ storage runtime wiring only |
| **Application** (`app/application`) | ❌ never imports `fastapi` or `app.api` | — | ✅ `AIProvider`, repository/UoW interfaces, domain schemas | ❌ never imports the factory or a concrete provider | ✅ `get_logger`, exceptions, `AuthenticatedPrincipal` | ❌ never imports SQLAlchemy models |
| **Domain** (`app/domain`) | ❌ never | ❌ never | — | ❌ never | ❌ never (no dependency on `app.core`) | ❌ never |
| **Providers** (`app/providers`) | ❌ never | ❌ never | ✅ implements `AIProvider`, uses domain models/schemas | — | ✅ `Settings`, `ConfigurationError`, logging | ❌ not used |
| **Core** (`app/core`) | ❌ never | ❌ never | ❌ never | ❌ never | — | ❌ not used |
| **Infrastructure** (`app/infrastructure/storage`) | ❌ never | ❌ never | ✅ implements repository/UoW interfaces | ❌ never | ✅ logging, exceptions, config URL parsing | — |

## Explicit Rules (Verified Against Source)

- **Domain does not import API, providers, or SQLAlchemy.** `app/domain/*` imports only `pydantic`, the standard library, and other `app.domain` modules. Persistence contracts are interfaces and dataclasses.
- **Application does not import FastAPI, the provider factory, or SQLAlchemy models.** Workflow, identity, and history services depend on domain interfaces.
- **API does not import concrete providers directly.** `app/api/dependencies.py` imports `app.providers.factory.create_ai_provider` (the factory), not `MockAIProvider`, `MicrosoftFoundryProvider`, or `AmazonBedrockProvider`. Storage implementations are constructed in API dependencies, not in routes.
- **Provider implementations depend on domain interfaces.** `MockAIProvider`, `MicrosoftFoundryProvider`, and `AmazonBedrockProvider` implement `AIProvider`. The factory imports `AIProvider` as its return type and `app.core.config`/`app.core.exceptions` for settings and error translation. The two real LLM adapters also import `app.providers.common`.
- **SQLAlchemy stays in infrastructure.** ORM models, engine, session, and repository implementations live under `app/infrastructure/storage/`.

## Where FastAPI-Specific Typing Is Allowed

`fastapi.Depends` and `fastapi.APIRouter` appear only in `app/api/dependencies.py` and `app/api/routes/*.py`. Nowhere else in the codebase (`app/application`, `app/domain`, `app/providers`, `app/core`, `app/infrastructure/storage`) is `fastapi` imported.

## Where Cloud SDKs Are Allowed

Azure SDK imports are allowed only inside `app/providers/microsoft_foundry/`. boto3 imports are allowed only inside `app/providers/amazon_bedrock/`. `app/providers/common/` maps structured LLM output onto domain models and must not import Azure or AWS SDKs. Domain, application, and API modules must not import cloud SDKs. Persistence uses PostgreSQL through SQLAlchemy/psycopg, not Azure or AWS database SDKs.
