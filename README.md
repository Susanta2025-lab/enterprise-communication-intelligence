# Enterprise Communication Intelligence Platform

**ECI Platform**

ECI Platform is a production-oriented AI platform that transforms business communications into structured, actionable intelligence. Rather than being limited to email automation, it is designed as a modular enterprise platform capable of supporting multiple communication channels, AI providers, and cloud environments through a provider-independent architecture.

The project is being developed as a practical demonstration of **AI Solution Architecture**, combining modern software engineering, enterprise architecture, and cloud-native AI integration.

---

## Project Goals

* Build a production-oriented AI application using Clean Architecture principles.
* Learn and compare **Microsoft Foundry** and **Amazon Bedrock** using the same codebase.
* Design a provider-independent architecture where business logic remains independent of AI providers and cloud platforms.
* Demonstrate enterprise software engineering practices suitable for AI Engineer and AI Solution Architect roles.
* Build a maintainable platform that can evolve beyond email into enterprise communication intelligence.

---

## Current Features

### Application Foundation

* FastAPI application foundation
* Centralized configuration management (Pydantic Settings)
* Structured logging
* Request correlation (`request_id` / `X-Request-ID`)
* Latency telemetry (`duration_ms`)
* Privacy-safe operational logs
* Framework-independent exception hierarchy
* OpenAPI / Swagger documentation
* Health and readiness endpoints

### Domain Layer

* Provider-independent communication domain
* Communication request and analysis models
* Strong validation using Pydantic v2
* Domain interfaces separated from infrastructure

### AI Architecture

* Provider abstraction through the `AIProvider` interface
* Configuration-driven provider factory
* Deterministic `MockAIProvider` for offline development and testing
* Production-capable `MicrosoftFoundryProvider`
* Production-capable `AmazonBedrockProvider`
* Shared LLM analysis contract in `app/providers/common/`
* Microsoft Entra ID authentication using `DefaultAzureCredential`
* Amazon Bedrock authentication using the boto3 credential chain
* Structured model output using JSON Schema (Responses API and Converse)
* Constructor-based dependency injection
* Communication analysis service
* Provider-independent orchestration

### Deployment

* One provider-independent Docker image for local, Azure, and AWS
* Local Docker Compose with `MockAIProvider`
* Azure Container Apps with user-assigned Managed Identity and Microsoft Foundry
* Amazon ECS on Fargate with an ECS Task Role and Amazon Bedrock
* No cloud credentials baked into the application image

### Observability

* Structured JSON telemetry on stdout (same image on Azure and AWS)
* Server-generated `X-Request-ID` for operational correlation
* Azure Log Analytics and native Container Apps metrics
* AWS CloudWatch Logs and standard ECS CPU/memory metrics
* Scale-to-zero / desiredCount=0 when idle

### REST API

* Versioned REST API
* `POST /api/v1/communications/analyze`
* Request validation
* Structured error handling
* Reusable domain schemas
* OpenAPI documentation

### Engineering

* Clean Architecture
* Comprehensive automated testing
* Technical documentation
* Architecture Decision Records (ADRs)
* Mermaid architecture diagrams

---

## Current Project Status

### Completed

* ✅ Phase 1 – Foundation
* ✅ Phase 2 – Provider-independent Communication Domain
* ✅ Phase 3 – Provider Abstraction
* ✅ Phase 4 – Communication Analysis Service
* ✅ Phase 5 – REST API
* ✅ Phase 6A – Microsoft Foundry Integration
* ✅ Phase 6B – Amazon Bedrock Integration
* ✅ Phase 6C – Deployment Foundation
* ✅ Phase 6 – Cloud Integration
* ✅ Phase 7A – Application Telemetry Foundation
* ✅ Phase 7B – Azure Observability Integration
* ✅ Phase 7C – AWS Observability Integration
* ✅ Phase 7D – Observability Documentation
* ✅ Phase 7 – Observability

---

## Architecture

```text
                    Client
                      │
                      ▼
               FastAPI REST API
                      │
                      ▼
       CommunicationAnalysisService
                      │
                      ▼
              AIProvider Interface
                      │
        ┌─────────────┼─────────────────┐
        │             │                 │
        ▼             ▼                 ▼
 MockAIProvider  MicrosoftFoundryProvider AmazonBedrockProvider
                      │                 │
                      └────────┬────────┘
                               ▼
                    providers/common
              (ECI structured-analysis contract)
                      │                 │
                      ▼                 ▼
               Microsoft Foundry    Amazon Bedrock
                  GPT-5.4-mini     Claude Haiku 4.5
```

The application and business layers depend only on the `AIProvider` interface. Provider selection is configuration-driven through `AI_PROVIDER`. `MockAIProvider` remains a deterministic offline path. `MicrosoftFoundryProvider` and `AmazonBedrockProvider` reuse the shared ECI structured-analysis contract in `app/providers/common/` while keeping Azure and AWS SDKs inside their own packages.

Microsoft Foundry authenticates with Microsoft Entra ID through `DefaultAzureCredential`. Amazon Bedrock authenticates with boto3's standard credential chain. Neither adapter stores static cloud keys in ECI Settings.

The same Docker image runs locally with the mock provider, on Azure Container Apps with Foundry, and on Amazon ECS Fargate with Bedrock. Cloud differences are environment variables and workload identity, not separate applications.

```text
same ECI Docker image
├── local Docker / mock
├── Azure Container Apps / Foundry
└── ECS Fargate / Bedrock
```

Local:

```text
REST API → CommunicationAnalysisService → AIProvider → MockAIProvider
```

Azure:

```text
REST API
→ CommunicationAnalysisService
→ MicrosoftFoundryProvider
→ DefaultAzureCredential
→ User-Assigned Managed Identity
→ Microsoft Foundry
```

AWS:

```text
REST API
→ CommunicationAnalysisService
→ AmazonBedrockProvider
→ boto3
→ ECS container credential provider
→ ECS Task Role
→ Amazon Bedrock
```

Amazon Bedrock is implemented, covered by offline tests, and live-verified through the ECI application. Azure Container Apps and ECS Fargate hosting are implemented and live-verified. Phase 7 observability uses the same stdout JSON on both clouds: Azure Log Analytics plus native Container Apps metrics, and AWS CloudWatch Logs plus standard ECS metrics. Operator commands live in `deployment/azure/` and `deployment/aws/`. Details: [`docs/cloud/observability.md`](docs/cloud/observability.md).

---

## Project Structure

```text
app/
├── api/
├── application/
├── core/
├── domain/
├── infrastructure/
├── providers/
└── schemas/

docs/
├── api/
├── architecture/
├── cloud/
├── decisions/
├── diagrams/
└── roadmap/

tests/
├── integration/
├── providers/
└── unit/

deployment/
├── azure/
├── aws/
└── docker/
```

---

## Technology Stack

### Backend

* Python 3.12
* FastAPI
* Pydantic v2
* Uvicorn

### Quality & Testing

* Pytest
* Ruff

### AI Architecture

* Provider Abstraction
* Dependency Injection
* Clean Architecture

### Cloud & AI Services

**Implemented**

* Microsoft Foundry
* Microsoft Entra ID authentication
* Azure AI Projects SDK
* OpenAI Responses API
* GPT-5.4-mini model integration
* Amazon Bedrock (implemented, regression-tested, and live-verified)
* Amazon Bedrock Converse API
* Claude Haiku 4.5 baseline
* boto3 standard credential chain
* Docker image (Python 3.12, non-root)
* Azure Container Registry and Azure Container Apps
* Amazon ECR and Amazon ECS Fargate
* User-assigned Managed Identity (Azure)
* ECS Task Role / Task Execution Role (AWS)
* Azure Log Analytics and native Container Apps metrics
* Amazon CloudWatch Logs and standard ECS metrics

**Later**

* Azure Key Vault
* AWS Secrets Manager
* Distributed tracing / OpenTelemetry
* Custom metrics, dashboards, and alerts
* CI/CD automation

---

## AI Provider Configuration

ECI selects the AI backend through configuration.

For deterministic offline development and testing:

```env
AI_PROVIDER=mock
```

For Microsoft Foundry:

```env
AI_PROVIDER=microsoft_foundry
FOUNDRY_PROJECT_ENDPOINT=<your-foundry-project-endpoint>
FOUNDRY_MODEL_DEPLOYMENT=<your-model-deployment-name>
```

Microsoft Foundry authentication uses `DefaultAzureCredential`; no Azure API key is required.

For local development, authenticate with the Azure CLI before starting the application:

```bash
az login
```

The current development Foundry deployment uses GPT-5.4-mini.

For Amazon Bedrock:

```env
AI_PROVIDER=amazon_bedrock
BEDROCK_REGION=eu-south-2
BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

Amazon Bedrock authentication uses boto3's standard credential chain. ECI does not store AWS access keys, secret keys, session tokens, or an AWS profile in Settings. For local development, authenticate with the AWS CLI (`aws login`) using the profile selected in the shell environment, then start the application.

The current Bedrock baseline is Claude Haiku 4.5 through a configurable EU inference profile. Live inference through the ECI application has been verified.

---

## Long-Term Vision

Although the initial MVP focuses on business communication analysis, the long-term vision is to evolve **ECI Platform** into a comprehensive **Enterprise Communication Intelligence Platform** that transforms scattered enterprise communications into structured, actionable intelligence.

The platform is designed to integrate with a broad ecosystem of enterprise and consumer communication systems, including:

* **Email platforms** (Gmail, Microsoft Outlook, Yahoo Mail, Microsoft Exchange, IMAP/SMTP providers)
* **Collaboration platforms** (Microsoft Teams, Slack)
* **Messaging platforms** (WhatsApp and other business messaging services)
* **CRM systems**
* **ERP systems**
* **Document repositories**
* **Calendar and scheduling systems**
* **Workflow automation platforms**

Beyond communication channels, ECI Platform is designed to support multiple AI providers, cloud platforms, and enterprise integrations through a modular, provider-independent architecture. This enables communication channels, AI providers, and deployment environments to evolve independently while preserving the core business logic.

---

## Development Roadmap

| Phase                                    | Status        |
| ---------------------------------------- | ------------- |
| Phase 1 – Foundation                     | ✅ Completed   |
| Phase 2 – Domain Model                   | ✅ Completed   |
| Phase 3 – Provider Abstraction           | ✅ Completed   |
| Phase 4 – Communication Analysis Service | ✅ Completed   |
| Phase 5 – REST API                       | ✅ Completed   |
| Phase 6 – Cloud Integration              | ✅ Completed   |
| ↳ Phase 6A – Microsoft Foundry           | ✅ Completed   |
| ↳ Phase 6B – Amazon Bedrock              | ✅ Completed   |
| ↳ Phase 6C – Deployment Foundation       | ✅ Completed   |
| Phase 7 – Observability                  | ✅ Completed   |
| ↳ Phase 7A – Application Telemetry       | ✅ Completed   |
| ↳ Phase 7B – Azure Observability         | ✅ Completed   |
| ↳ Phase 7C – AWS Observability           | ✅ Completed   |
| ↳ Phase 7D – Documentation               | ✅ Completed   |
| Phase 8 – Future Roadmap                 | ⏳ Not Started |

---

## Documentation

Technical documentation is available under the `docs/` directory:

* API documentation
* Architecture documentation
* Architecture Decision Records (ADRs)
* Mermaid diagrams
* Development roadmap
* Cloud planning documents
* Azure and AWS deployment runbooks (`deployment/azure/`, `deployment/aws/`)

---

## Current Limitations

The current implementation intentionally focuses on architecture and application design.

Not yet implemented:

* Authentication & authorization for ECI application users
* Persistent storage
* Workflow automation
* Enterprise communication integrations
* Production-hardened ingress (stable load balancer and TLS termination)
* CI/CD automation
* Distributed tracing, custom metrics, dashboards, alerts, and SLOs

---

## License

MIT License
