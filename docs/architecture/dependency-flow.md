# Dependency Flow

This documents the *actual* import relationships enforced in the current codebase, not aspirational ones.

## Dependency Matrix

| From ↓ / To → | API | Application | Domain | Providers | Core | Infrastructure |
|---|---|---|---|---|---|---|
| **API** (`app/api`) | — | ✅ via `CommunicationAnalysisService` type | ✅ schemas (`CommunicationRequest`, `CommunicationAnalysisResult`) | ✅ only the factory (`create_ai_provider`), never a concrete provider class | ✅ `get_settings` | ❌ not used |
| **Application** (`app/application`) | ❌ never imports `fastapi` or `app.api` | — | ✅ `AIProvider`, domain schemas | ❌ never imports the factory or a concrete provider | ✅ `get_logger` | ❌ not used |
| **Domain** (`app/domain`) | ❌ never | ❌ never | — | ❌ never | ❌ never (no dependency on `app.core`) | ❌ never |
| **Providers** (`app/providers`) | ❌ never | ❌ never | ✅ implements `AIProvider`, uses domain models/schemas | — | ✅ `Settings`, `ConfigurationError` (in the factory) | ❌ not used |
| **Core** (`app/core`) | ❌ never | ❌ never | ❌ never | ❌ never | — | ❌ not used |
| **Infrastructure** (`app/infrastructure`) | — | — | — | — | — | Empty scaffold packages (`monitoring`, `parsers`, `storage`); no code exists to define dependencies |

## Explicit Rules (Verified Against Source)

- **Domain does not import API or providers.** `app/domain/*` imports only `pydantic`, the standard library, and other `app.domain` modules. Confirmed by inspecting `app/domain/enums.py`, `app/domain/models/`, `app/domain/schemas/`, `app/domain/interfaces/ai_provider.py`.
- **Application does not import FastAPI or the provider factory.** `app/application/services/communication_analysis.py` imports only `app.application.exceptions`, `app.core.logging`, `app.domain.interfaces`, and `app.domain.schemas`. It never imports `fastapi` or `app.providers.factory`.
- **API does not import concrete providers directly.** `app/api/dependencies.py` imports `app.providers.factory.create_ai_provider` (the factory), not `app.providers.mock.provider.MockAIProvider`. `app/api/routes/communications.py` imports only `app.api.dependencies`, `app.application.services`, `app.core.logging`, `app.domain.schemas`, and `app.schemas.errors` — never a provider module.
- **Provider implementations depend on domain interfaces.** `app/providers/mock/provider.py` imports `app.domain.interfaces.AIProvider` and implements it; `app/providers/factory.py` imports `app.domain.interfaces.AIProvider` as its return type and `app.core.config`/`app.core.exceptions` for settings and error translation.

## Where FastAPI-Specific Typing Is Allowed

`fastapi.Depends` and `fastapi.APIRouter` appear only in `app/api/dependencies.py` and `app/api/routes/*.py`. Nowhere else in the codebase (`app/application`, `app/domain`, `app/providers`, `app/core`) is `fastapi` imported.

## Where Cloud SDKs Are Allowed

Nowhere yet. No Azure SDK or `boto3` import exists anywhere in the repository. `app/providers/aws/__init__.py` and `app/providers/azure/__init__.py` are empty files; when populated, cloud SDK imports must remain confined to those packages.
