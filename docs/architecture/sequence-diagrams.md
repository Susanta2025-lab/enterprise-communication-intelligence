# Sequence Diagrams

These diagrams describe the request flows implemented as of Phase 6A. Source `.mmd` files live in [`docs/diagrams/`](../diagrams/README.md); the successful and failure communication-analysis flows are combined in [`request-flow.mmd`](../diagrams/request-flow.mmd). The sequence below uses `MockAIProvider` as the default local provider; `MicrosoftFoundryProvider` occupies the same `AIProvider` slot when selected. This page also documents the health request flow, which has no dedicated `.mmd` file since it involves no failure branching worth diagramming separately.

## Successful Communication-Analysis Request

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(communications.py)
    participant Service as CommunicationAnalysisService
    participant Provider as AIProvider
    participant Mock as MockAIProvider

    Client->>Route: POST /api/v1/communications/analyze
    Route->>Route: Validate CommunicationRequest (Pydantic)
    Route->>Service: analyze(request)
    Service->>Provider: analyze(request)
    Provider->>Mock: analyze(request)
    Mock-->>Provider: CommunicationAnalysisResult
    Provider-->>Service: CommunicationAnalysisResult
    Service-->>Route: CommunicationAnalysisResult
    Route-->>Client: 200 OK + JSON body
```

## Provider Failure Flow

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(communications.py)
    participant Service as CommunicationAnalysisService
    participant Provider as AIProvider
    participant Handler as Exception Handler<br/>(app/main.py)

    Client->>Route: POST /api/v1/communications/analyze
    Route->>Route: Validate CommunicationRequest (Pydantic)
    Route->>Service: analyze(request)
    Service->>Provider: analyze(request)
    Provider--xService: raises Exception
    Service->>Service: log communication_analysis_failed
    Service--xRoute: raises AnalysisFailedError
    Route--xHandler: propagates ECIPlatformError
    Handler->>Handler: log application_error
    Handler-->>Client: 500 + {"detail": "..."}
```

## Configuration Error Flow (Unsupported Provider)

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(communications.py)
    participant Dep as get_ai_provider (dependency)
    participant Factory as create_ai_provider
    participant Handler as Exception Handler<br/>(app/main.py)

    Client->>Route: POST /api/v1/communications/analyze
    Route->>Dep: resolve CommunicationAnalysisService
    Dep->>Factory: create_ai_provider(settings)
    Factory--xDep: raises ConfigurationError (unsupported AI_PROVIDER)
    Dep--xRoute: propagates ConfigurationError
    Route--xHandler: propagates ECIPlatformError
    Handler-->>Client: 500 + {"detail": "Unsupported AI provider '...'. Supported providers: mock, microsoft_foundry"}
```

## Health Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant Route as FastAPI Route<br/>(health.py)
    participant Settings as Settings (app/core/config.py)

    Client->>Route: GET /health
    Route-->>Client: 200 OK + {"status": "healthy"}

    Client->>Route: GET /api/v1/health
    Route->>Settings: get_settings()
    Settings-->>Route: app_name, app_version, app_env
    Route-->>Client: 200 OK + HealthResponse

    Client->>Route: GET /api/v1/readiness
    Route->>Settings: get_settings()
    Settings-->>Route: settings loaded successfully
    Route-->>Client: 200 OK + {"status": "ready"}
```

Health and readiness routes never call `CommunicationAnalysisService` or any `AIProvider` — they only read configuration.
