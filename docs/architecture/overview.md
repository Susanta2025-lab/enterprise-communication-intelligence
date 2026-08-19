# Architecture Overview

## Implemented Request Path

```text
Client
  ↓
FastAPI REST API        (app/api)
  ↓
CommunicationAnalysisService   (app/application/services)
  ↓
AIProvider interface    (app/domain/interfaces)
  ↓
MockAIProvider | MicrosoftFoundryProvider | AmazonBedrockProvider
```

Every layer in this path is implemented and exercised by tests spanning `tests/unit` and `tests/integration`. Automated tests stay offline; Microsoft Foundry and Amazon Bedrock are exercised through mocked SDK clients. Live ECI → Bedrock verification is complete.

## Purpose of Each Layer

- **FastAPI REST API (`app/api`)** — HTTP transport. Defines routes (`app/api/routes/`), the API router assembly (`app/api/router.py`), and dependency wiring (`app/api/dependencies.py`). Contains no business logic; every route validates input via Pydantic and delegates to a service.
- **Application service (`app/application`)** — Orchestrates use cases. `CommunicationAnalysisService` receives an already-validated `CommunicationRequest`, calls the injected `AIProvider`, translates provider failures into `AnalysisFailedError`, and emits structured logs. It has no knowledge of FastAPI, HTTP, or which concrete provider is behind the interface.
- **Domain (`app/domain`)** — Provider-independent business objects: enums (`SourceType`, `PriorityLevel`, `MessageCategory`), models (`CommunicationMessage`, `MessageMetadata`, `CommunicationAnalysis`, `Summary`, `Priority`, `ActionItem`, `DraftReply`), schemas (`CommunicationRequest`, `CommunicationAnalysisResult`), and the `AIProvider` interface. Domain code imports neither FastAPI nor any cloud SDK.
- **Providers (`app/providers`)** — Concrete implementations of `AIProvider`. `MockAIProvider`, `MicrosoftFoundryProvider`, and `AmazonBedrockProvider` are implemented. The two real LLM adapters share `app/providers/common/`. `app/providers/factory.py` selects a provider from configuration.
- **Core (`app/core`)** — Cross-cutting concerns: `config.py` (Pydantic Settings), `logging.py` (structlog configuration), `telemetry.py` (request-safe `duration_ms` and `error_class` helpers), `exceptions.py` (the base application exception hierarchy), `security.py` (OIDC JWT validation and `AuthenticatedPrincipal`). HTTP `request_id` binding lives in `app/api/middleware.py`.

## Provider Independence

The application service and every layer above it depend only on `app.domain.interfaces.AIProvider`, never on `MockAIProvider`, `MicrosoftFoundryProvider`, `AmazonBedrockProvider`, or any other concrete provider class. Provider selection happens in exactly one place — `app/providers/factory.py` — driven by the `AI_PROVIDER` setting. This means:

- Swapping providers requires no change to `CommunicationAnalysisService` or any route.
- Amazon Bedrock was added as `app/providers/amazon_bedrock/` plus one factory branch, without changing application or API code.

## Current Implementation Boundary

The system is fully synchronous and has no persistence. When `AUTH_MODE=oidc`, `POST /api/v1/communications/analyze` requires a JWT bearer token; health and readiness remain public. Production clouds use `AUTH_MODE=oidc`. Live Entra is the first identity provider; ECI remains provider-independent. Application-user identity, runtime workload identity (Foundry UAMI / Bedrock task role), and GitHub deploy identity stay separate. Azure real-bearer authorized inference is verified over HTTPS. AWS real-bearer TLS verification is not claimed. When `AI_PROVIDER=mock`, there are no external network calls. When `AI_PROVIDER=microsoft_foundry`, inference goes to Microsoft Foundry using Entra ID. When `AI_PROVIDER=amazon_bedrock`, inference goes to Amazon Bedrock through Converse. Automated tests do not execute those cloud paths. Live ECI → Foundry and ECI → Bedrock workload inference was verified in Phase 6. Phase 8D verified one authorized Foundry call after application-user auth; AWS authorized Bedrock after a real bearer is deferred until TLS.

## Phase 8 identity, deployment, and ingress

```text
APPLICATION USER

    Microsoft Entra ID
            |
          JWT
            |
            v
      ECI REST API
            |
 CommunicationAnalysisService
            |
        AIProvider
      /            \
Microsoft Foundry  Amazon Bedrock
     UAMI          ECS Task Role

DEPLOYMENT

         GitHub Actions
           /          \
        OIDC          OIDC
         |              |
 Azure deploy UAMI   AWS deploy IAM role
         |              |
        ACR            ECR
         |              |
        ACA            ECS

INGRESS

Azure live: HTTPS → Container Apps → ECI
AWS current: operator /32 HTTP → ECS task → ECI (verification-only)
AWS verified, not retained: HTTPS / domain / ACM → ALB → ECS
```

See [`identity.mmd`](../diagrams/identity.mmd), [`cicd.mmd`](../diagrams/cicd.mmd), and [`ingress.mmd`](../diagrams/ingress.mmd).

## Future Extensibility

Phase 8 identity separation is implemented: application-user OIDC JWT, Azure/AWS workload identity, and GitHub OIDC deploy identities. Phase 7 observability is implemented: portable structured JSON on stdout, `request_id` / `X-Request-ID` correlation, `duration_ms`, and `error_class`. Azure retains logs in Log Analytics and exposes native Container Apps metrics. AWS retains logs in CloudWatch via awslogs and exposes standard ECS CPU/memory metrics. Distributed tracing, custom metrics, dashboards, and alerts remain deferred. Additional providers can still be added behind `AIProvider` and the factory without changing the application or API layers. See [Provider Abstraction](provider-abstraction.md), [Observability](../cloud/observability.md), [Authentication](../cloud/authentication.md), and [`docs/cloud/`](../cloud/README.md).
