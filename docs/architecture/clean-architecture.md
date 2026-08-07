# Clean Architecture in ContextMesh

ContextMesh applies clean-architecture-style layering: dependency direction points inward, toward stable, framework-independent code, and outward layers own the framework and infrastructure details.

## Dependency Direction

```text
API  →  Application  →  Domain  ←  Providers
                          ↑
                        Core
```

- `app/api` depends on `app/application` (indirectly, via dependencies) and on `app/domain` schemas.
- `app/application` depends on `app/domain` (models, schemas, interfaces) and `app/core` (logging).
- `app/providers` depends on `app/domain` (implements `AIProvider`, uses domain models/schemas) and `app/core` (config, exceptions).
- `app/domain` depends on nothing else in the application — it is the innermost, most stable layer.

This matches the direction required by `.cursor/rules/contextmesh.mdc`: domain code must remain independent of FastAPI, Azure SDKs, and AWS SDKs.

## Stable Inner Layers

`app/domain` is the most stable part of the codebase:

- It defines enums, Pydantic models, schemas, and the `AIProvider` interface.
- It imports only Pydantic and the Python standard library — never `fastapi`, `httpx` (as an HTTP client), or any cloud SDK.
- Nothing in `app/domain` changes when a new provider, route, or deployment target is added.

## Infrastructure at the Edges

Framework and infrastructure concerns live at the outer edges:

- **FastAPI** is confined to `app/api` (routes, dependency wiring, router assembly) and `app/main.py` (application construction, lifespan, exception handlers).
- **Provider-specific code** is confined to `app/providers/<provider_name>/`. Today only `app/providers/mock/` has an implementation; `app/providers/aws/` and `app/providers/azure/` are empty scaffold packages reserved for future cloud SDK usage.
- **Configuration and logging** (`app/core/config.py`, `app/core/logging.py`) are the only places environment variables and `structlog`/`logging` setup are touched.

## Why Domain Code Is Independent of FastAPI and Cloud SDKs

- **Testability:** `app/domain` and `app/application` are tested with plain Python objects (see `tests/unit/domain`, `tests/unit/application`) — no FastAPI `TestClient` or cloud credentials required.
- **Provider replaceability:** Because `CommunicationAnalysisService` only knows about `AIProvider`, a future Azure or AWS adapter can be introduced without modifying application or domain code — only `app/providers/factory.py` gains a new branch.
- **Avoiding lock-in:** Domain models (`CommunicationMessage`, `CommunicationAnalysis`, etc.) do not encode any vendor-specific concepts, keeping the business vocabulary reusable across future channels (Slack, Teams, WhatsApp, etc. — represented today only as `SourceType` enum values with no adapters).

## Trade-offs (Current State)

- **Not full DDD:** ContextMesh borrows clean architecture's *layering and dependency direction*, but does not implement full Domain-Driven Design — there are no aggregates, domain events, repositories, or a ubiquitous-language modeling process. The "domain" layer here is intentionally lightweight: Pydantic models with validation, plus one interface.
- **No application-service abstraction beyond one use case:** `app/application/services` currently contains a single service (`CommunicationAnalysisService`). No generic use-case base class or command/query separation has been introduced, per the project rule to avoid premature abstraction.
- **Framework coupling still exists at the edges by design:** `app/api` necessarily depends on FastAPI (`Depends`, `APIRouter`), and `app/providers` will necessarily depend on cloud SDKs once Azure/AWS adapters are added. This is intentional — clean architecture pushes volatility to the edges rather than eliminating it.
- **Core is shared, not layered further:** `app/core` (config, logging, exceptions) is used by every layer. It is deliberately minimal and framework-agnostic (aside from being read by FastAPI's lifespan hook in `app/main.py`), rather than being split into its own strict sub-layers.
