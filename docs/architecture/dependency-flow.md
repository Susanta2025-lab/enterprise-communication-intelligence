# Dependency Flow

This documents the *actual* import relationships enforced in the current codebase, not aspirational ones.

## Dependency Matrix

| From ↓ / To → | API | Application | Domain | Providers | Core | Infrastructure storage | Infrastructure connectors |
|---|---|---|---|---|---|---|---|
| **API** (`app/api`) | — | ✅ workflow, identity, history, AI service types | ✅ schemas and records | ✅ only the factory (`create_ai_provider`), never a concrete provider class | ✅ `get_settings`, security, exceptions | ✅ storage runtime wiring only | ❌ does not import concrete connectors |
| **Application** (`app/application`) | ❌ never imports `fastapi` or `app.api` | — | ✅ `AIProvider`, `CommunicationConnector`, repository/UoW interfaces, domain schemas | ❌ never imports the factory or a concrete provider | ✅ `get_logger`, exceptions, `AuthenticatedPrincipal` | ❌ never imports SQLAlchemy models | ❌ never imports Gmail/Graph/fake adapters |
| **Domain** (`app/domain`) | ❌ never | ❌ never | — | ❌ never | ❌ never (no dependency on `app.core`) | ❌ never | ❌ never |
| **Providers** (`app/providers`) | ❌ never | ❌ never | ✅ implements `AIProvider`, uses domain models/schemas | — | ✅ `Settings`, `ConfigurationError`, logging | ❌ not used | ❌ not used |
| **Core** (`app/core`) | ❌ never | ❌ never | ❌ never | ❌ never | — | ❌ not used | ❌ not used |
| **Infrastructure storage** (`app/infrastructure/storage`) | ❌ never | ❌ never | ✅ implements repository/UoW interfaces | ❌ never | ✅ logging, exceptions, config URL parsing | — | ❌ not used |
| **Infrastructure connectors** (`app/infrastructure/connectors`) | ❌ never | ❌ never | ✅ implements `CommunicationConnector`, returns `CommunicationMessage` | ❌ never `AIProvider` | ✅ connector-neutral exceptions, logging helpers | ❌ never SQLAlchemy ORM | — |

## Connector dependency direction

Domain defines `CommunicationConnector`. Application depends on that interface. Infrastructure implements it. Application and infrastructure connectors do not depend on each other.

```text
                    Domain
           CommunicationConnector
              ↗                 ↖
 Application                     Infrastructure
 depends on interface            implements adapters
                                 (fake / Gmail / Graph)
```

API does not import concrete connectors today. There is no connector factory in the repository.

Connectors do not depend on API, application services (including `ConnectorAccountService`), storage ORM, or `AIProvider`.

## Explicit Rules (Verified Against Source)

- **Domain does not import API, providers, SQLAlchemy, or connector adapters.** `app/domain/*` imports only `pydantic`, the standard library, and other `app.domain` modules. Persistence and connector contracts are interfaces and dataclasses.
- **Application does not import FastAPI, the provider factory, SQLAlchemy models, or vendor mailbox types.** Workflow, identity, history, ingestion, connector-account, and workflow-action services depend on domain interfaces. `CommunicationIngestionService` takes `CommunicationConnector`; it does not import `GmailCommunicationConnector` or `MicrosoftGraphCommunicationConnector`. `WorkflowActionService` uses `WorkflowActionRepository`; it does not import connector adapters or an executor.
- **API does not import concrete AI providers or concrete connectors.** `app/api/dependencies.py` imports `app.providers.factory.create_ai_provider` (the factory), not `MockAIProvider`, `MicrosoftFoundryProvider`, or `AmazonBedrockProvider`. Storage implementations are constructed in API dependencies, not in routes. Connector adapters are not wired in the API. Phase 11C adds workflow routes that depend on `WorkflowActionService` and `require_authenticated_communications_workflow`.
- **Provider implementations depend on domain interfaces.** `MockAIProvider`, `MicrosoftFoundryProvider`, and `AmazonBedrockProvider` implement `AIProvider`. The factory imports `AIProvider` as its return type and `app.core.config`/`app.core.exceptions` for settings and error translation. The two real LLM adapters also import `app/providers/common`.
- **SQLAlchemy stays in infrastructure storage.** ORM models, engine, session, and repository implementations live under `app/infrastructure/storage/`.
- **Mailbox HTTP stays in infrastructure connectors.** Gmail and Microsoft Graph adapters use `httpx` REST. They do not add a Gmail SDK, Microsoft Graph SDK, or MSAL dependency inside ECI.

## Where FastAPI-Specific Typing Is Allowed

`fastapi.Depends` and `fastapi.APIRouter` appear only in `app/api/dependencies.py` and `app/api/routes/*.py`. Nowhere else in the codebase (`app/application`, `app/domain`, `app/providers`, `app/core`, `app/infrastructure/storage`, `app/infrastructure/connectors`) is `fastapi` imported.

## Where Cloud SDKs Are Allowed

Azure SDK imports are allowed only inside `app/providers/microsoft_foundry/`. boto3 imports are allowed only inside `app/providers/amazon_bedrock/`. `app/providers/common/` maps structured LLM output onto domain models and must not import Azure or AWS SDKs. Domain, application, and API modules must not import cloud SDKs. Persistence uses PostgreSQL through SQLAlchemy/psycopg, not Azure or AWS database SDKs. Gmail and Graph mailbox access uses REST via `httpx` in `app/infrastructure/connectors/`; those adapters must not import Azure or AWS SDKs.
