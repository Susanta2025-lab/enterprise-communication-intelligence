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
* Azure Container Apps managed HTTPS (`allowInsecure=false`, operator `/32`)
* AWS ALB architecture verified then removed (domain/ACM required before HTTPS)
* No cloud credentials baked into the application image

### Authentication

* Provider-independent OIDC JWT validation
* Permission authorization (`communications:analyze` for analyze/history; `communications:workflow` for proposal/approval; `communications:send` for execute)
* Fail-closed production (`APP_ENV=production` requires `AUTH_MODE=oidc`)
* First live identity provider: Microsoft Entra ID (single-tenant resource application)

### CI/CD

* GitHub Actions CI (automatic: pip check, ruff, pytest, plus PostgreSQL integration)
* Manual multi-cloud CD (`workflow_dispatch` target `azure` | `aws` | `both`)
* GitHub OIDC federation (no long-lived deploy secrets)
* Build-once SHA and `stable` image tags

### Observability

* Structured JSON telemetry on stdout (same image on Azure and AWS)
* Server-generated `X-Request-ID` for operational correlation
* Azure Log Analytics and native Container Apps metrics
* AWS CloudWatch Logs and standard ECS CPU/memory metrics
* Scale-to-zero / desiredCount=0 when idle

### REST API

* Versioned REST API
* `POST /api/v1/communications/analyze`
* Optional `analysis_id` when authenticated history storage succeeds
* `GET /api/v1/analyses` and `GET/DELETE /api/v1/analyses/{analysis_id}`
* `POST /api/v1/workflow-actions`, `GET /api/v1/workflow-actions`, `GET /api/v1/workflow-actions/{action_id}`
* `POST /api/v1/workflow-actions/{action_id}/approve` and `.../reject`
* `POST /api/v1/workflow-actions/{action_id}/execute` (`communications:send`)
* Request validation
* Structured error handling
* Reusable domain schemas
* OpenAPI documentation

### Persistence

* PostgreSQL production persistence architecture (SQLAlchemy 2.x, Alembic, psycopg 3)
* Authenticated user ownership via OIDC `issuer` + `subject` → internal user UUID
* Analysis history with SQL-scoped ownership isolation
* User-owned `workflow_actions` with proposed/approved reply snapshots and no analysis FK
* Raw communication body is not stored
* PostgreSQL CI validation (ephemeral `postgres:16`; run `32336909759`)
* SQLite for default local tests only

### Communication Connectors

* Vendor-neutral `CommunicationConnector` contract
* Gmail read-only REST adapter (no Gmail SDK)
* Microsoft Graph read-only REST adapter (no Graph SDK / MSAL inside ECI)
* User-owned connector accounts with opaque `credential_ref`
* Connector ingestion into the existing analysis workflow (below the HTTP surface)
* Controlled local live adapter verification for Gmail and Microsoft Graph, stopping at `CommunicationMessage`

Phase 10 does not include production OAuth, connector HTTP APIs, background synchronization, or automatic replies.

### Workflow Automation

* Approval-gated `WorkflowAction` domain (`REPLY` only) with an explicit state machine
* AI `DraftReply` remains a suggestion; analyze does not create a workflow action
* Explicit proposal creation snapshots `draft_reply.body` into a PENDING action
* User approval copies the proposed snapshot; rejection retains it and cannot execute
* HTTP proposal/approval API under `/api/v1/workflow-actions` (`communications:workflow`)
* User-approved execute API under `POST /api/v1/workflow-actions/{action_id}/execute` (`communications:send`)
* Provider-neutral executor factory routes owned Gmail or Microsoft Graph accounts
* Real Gmail reply execution (`users/me/profile` + metadata + `messages.send`)
* Real Microsoft Graph reply execution (`POST /me/messages/{id}/reply`)
* Credential abstraction via `CommunicationCredentialResolver` (environment-backed local/dev lookup)
* Distinct analyze / workflow / send permissions
* Uncertain provider outcomes remain `EXECUTING` and return HTTP 503; they are not automatically retried

Phase 12 does not include automatic replies, production OAuth lifecycle, managed secret-store mailbox backends, retry/reconciliation, or exactly-once delivery.

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
* ✅ Phase 8A – Application Authentication
* ✅ Phase 8B – Production Ingress
* ✅ Phase 8C – GitHub Actions CI/CD
* ✅ Phase 8D – Cross-Cloud Verification
* ✅ Phase 8 – Production Hardening
* ✅ Phase 9A – Persistence Foundation
* ✅ Phase 9B – User Ownership & Analysis History
* ✅ Phase 9C – PostgreSQL Integration & CI
* ✅ Phase 9D – Cloud Strategy & Final Documentation
* ✅ Phase 9 – Persistence & User-Associated Data
* ✅ Phase 10A – Connector Architecture & Domain Contracts
* ✅ Phase 10B – Connector Accounts & Credential References
* ✅ Phase 10C – Gmail Read-Only Adapter
* ✅ Phase 10D – Microsoft Graph Read-Only Adapter
* ✅ Phase 10E – Documentation Finalization
* ✅ Phase 10 – Communication Connectors
* ✅ Phase 11A – Workflow Domain, State Machine & Authorization Foundation
* ✅ Phase 11B – Workflow Persistence & User Ownership
* ✅ Phase 11C – Workflow Proposal and Approval API
* ✅ Phase 11D – Action Execution Port + Deterministic Fake Executor
* ✅ Phase 11E – Integration, Documentation & Regression
* ✅ Phase 11 – Workflow Automation
* ✅ Phase 12A – Execution Target, Routing & Executability Foundation
* ✅ Phase 12B – Credential Resolution + Write-Scope Readiness
* ✅ Phase 12C – Microsoft Graph Reply Executor
* ✅ Phase 12D – Gmail Reply Executor
* ✅ Phase 12E – Execute API + communications:send
* ✅ Phase 12F – Failure Semantics, Privacy, Documentation & Regression
* ✅ Phase 12 – Production Communication Execution

---

## Architecture

```text
                    Client
                      │
                      ▼
               FastAPI REST API
                      │
                      ▼
     CommunicationAnalysisWorkflowService
           │                      │
           ▼                      ▼
CommunicationAnalysisService   AnalysisHistoryService
           │                      │
           ▼                      ▼
    AIProvider Interface     PostgreSQL repositories
           │
     ┌─────┼──────────────┐
     ▼     ▼              ▼
   Mock  Foundry       Bedrock
```

The application and business layers depend only on the `AIProvider` interface and persistence repository interfaces. Provider selection is configuration-driven through `AI_PROVIDER`. Persistence is configuration-driven through `DATABASE_URL`. `MockAIProvider` remains a deterministic offline path. `CommunicationAnalysisService` remains AI-only.

Phase 10 adds a vendor-neutral connector path below the HTTP product surface:

```text
CommunicationConnector
        ↑
vendor adapter (gmail | microsoft_graph)
        ↓
CommunicationMessage
        ↓
CommunicationIngestionService
        ↓
CommunicationAnalysisWorkflowService
        ↓
CommunicationAnalysisService
        ↓
AIProvider
```

Controlled local live Gmail and Graph checks stopped at `CommunicationMessage` and did not call Foundry, Bedrock, or PostgreSQL.

Phase 11 adds an approval-gated workflow path. Analyze still does not create or authorize actions:

```text
CommunicationAnalysis
        ↓
AI DraftReply (suggestion only)
        ↓
explicit WorkflowAction proposal (PENDING)
        ↓
user approve / reject
        ↓
approved snapshot (APPROVED) or REJECTED
```

Phase 12 adds user-approved real communication execution:

```text
POST /api/v1/workflow-actions/{id}/execute
        ↓
communications:send
        ↓
WorkflowActionExecutionService
        ↓
owned ACTIVE ConnectorAccount
        ↓
CommunicationActionExecutorFactory
        ↓
TX1 APPROVED → EXECUTING (commit, close UoW)
        ↓
credential resolver / access token
        ↓
Graph /reply  or  Gmail profile + metadata + send
        ↓
TX2 EXECUTED | FAILED
```

`CommunicationConnector` remains read-only. `CommunicationActionExecutor` is a separate write port. Uncertain provider or credential failure after TX1 returns HTTP 503 and leaves the row `EXECUTING`. There is no retry route and no automatic reply.

Microsoft Foundry authenticates with Microsoft Entra ID through `DefaultAzureCredential`. Amazon Bedrock authenticates with boto3's standard credential chain. Neither adapter stores static cloud keys in ECI Settings. Database identity is separate from user identity, AI workload identity, and GitHub deploy identity.

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

Amazon Bedrock is implemented, covered by offline tests, and live-verified through the ECI application in Phase 6. Azure Container Apps and ECS Fargate hosting are implemented and live-verified. Phase 7 observability uses the same stdout JSON on both clouds: Azure Log Analytics plus native Container Apps metrics, and AWS CloudWatch Logs plus standard ECS metrics. Operator commands live in `deployment/azure/` and `deployment/aws/`. Details: [`docs/cloud/observability.md`](docs/cloud/observability.md).

Application users authenticate with a Microsoft Entra ID JWT. Runtime Foundry/Bedrock identities and GitHub deploy identities stay separate. GitHub Actions builds the image once and deploys it through OIDC to Azure Container Apps and Amazon ECS.

```text
APPLICATION USER          RUNTIME AI                    DATABASE
Entra ID → JWT → ECI      ECI → Foundry UAMI            ECI → PostgreSQL
issuer+subject → users.id ECI → Bedrock task role       CI-proven; managed DB
                                                        not provisioned in Phase 9

DEPLOYMENT                INGRESS
GitHub → OIDC             Azure: HTTPS → ACA → ECI
→ Azure deploy UAMI       AWS current: /32 HTTP (verification-only)
→ AWS deploy IAM role     AWS ALB HTTPS: verified, not retained
```

Persistence is cloud-portable and PostgreSQL-compatible. It is not active-active multi-cloud replication. Details: [`docs/architecture/persistence.md`](docs/architecture/persistence.md), [`docs/cloud/persistence.md`](docs/cloud/persistence.md), [ADR-012](docs/decisions/ADR-012-postgresql-persistence-architecture.md), [ADR-013](docs/decisions/ADR-013-external-identity-mapping-and-user-owned-data.md), [ADR-014](docs/decisions/ADR-014-cloud-postgresql-deployment-strategy.md).

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
* SQLAlchemy 2.x
* Alembic
* psycopg 3
* PostgreSQL (production dialect; CI-proven)

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
* GitHub Actions CI/CD
* GitHub OIDC federation
* PostgreSQL persistence (SQLAlchemy / Alembic; CI `postgres:16`)

**Later**

* Azure Key Vault / AWS Secrets Manager mailbox secret backends (environment-backed local/dev credential lookup exists)
* Managed Azure PostgreSQL / Amazon RDS
* Distributed tracing / OpenTelemetry
* Custom metrics, dashboards, and alerts

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
| Phase 8 – Production Hardening           | ✅ Completed   |
| ↳ Phase 8A – Application Authentication  | ✅ Completed   |
| ↳ Phase 8B – Production Ingress          | ✅ Completed   |
| ↳ Phase 8C – GitHub Actions CI/CD        | ✅ Completed   |
| ↳ Phase 8D – Cross-Cloud Verification    | ✅ Completed   |
| Phase 9 – Persistence                    | ✅ Completed   |
| ↳ Phase 9A – Persistence Foundation      | ✅ Completed   |
| ↳ Phase 9B – User Ownership & History    | ✅ Completed   |
| ↳ Phase 9C – PostgreSQL Integration & CI | ✅ Completed   |
| ↳ Phase 9D – Cloud Strategy & Final Docs | ✅ Completed   |
| Phase 10 – Communication Connectors      | ✅ Completed   |
| ↳ Phase 10A – Connector Architecture     | ✅ Completed   |
| ↳ Phase 10B – Connector Accounts         | ✅ Completed   |
| ↳ Phase 10C – Gmail Read-Only Adapter    | ✅ Completed   |
| ↳ Phase 10D – Microsoft Graph Adapter    | ✅ Completed   |
| ↳ Phase 10E – Documentation Finalization | ✅ Completed   |
| Phase 11 – Workflow Automation           | ✅ Completed   |
| ↳ Phase 11A – Domain & Authorization     | ✅ Completed   |
| ↳ Phase 11B – Persistence & Ownership    | ✅ Completed   |
| ↳ Phase 11C – Proposal & Approval API    | ✅ Completed   |
| ↳ Phase 11D – Fake Execution Boundary    | ✅ Completed   |
| ↳ Phase 11E – Integration & Documentation| ✅ Completed   |
| Phase 12 – Production Communication Execution | ✅ Completed   |
| ↳ Phase 12A – Execution Target Foundation | ✅ Completed   |
| ↳ Phase 12B – Credential Resolution      | ✅ Completed   |
| ↳ Phase 12C – Graph Reply Executor       | ✅ Completed   |
| ↳ Phase 12D – Gmail Reply Executor       | ✅ Completed   |
| ↳ Phase 12E – Execute API + send         | ✅ Completed   |
| ↳ Phase 12F – Semantics, Privacy & Docs  | ✅ Completed   |

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

* Managed Azure PostgreSQL or Amazon RDS (Phase 9 is CI-proven, not cloud-provisioned)
* Production Gmail/Microsoft OAuth lifecycle, token refresh, and connector HTTP APIs
* Mailbox synchronization, webhooks, and attachments
* Automatic replies, retry/reconciliation, exactly-once delivery, or live-provider send validation
* Managed secret-store mailbox backends (Key Vault / Secrets Manager)
* AWS persistent HTTPS / custom domain (domain and ACM not configured)
* AWS real-bearer authorized requests (deferred until TLS)
* Phase 8B temporary IAM policy cleanup if still attached
* Distributed tracing, custom metrics, dashboards, alerts, and SLOs
* Database backup, PITR, HA, and cross-region DR

AWS ALB architecture was verified in Phase 8B and then torn down for cost control. Direct AWS task HTTP remains verification-only. Current cloud application environments do not have Phase 9 database configuration.

---

## License

MIT License
