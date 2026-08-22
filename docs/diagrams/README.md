# Diagrams

Mermaid source files for ECI Platform.

## Available Diagrams

| File | Represents |
|---|---|
| [`architecture.mmd`](architecture.mmd) | The implemented layered system through Phase 10: HTTP analyze path plus Gmail/Graph → `CommunicationConnector` → `CommunicationMessage` → `CommunicationIngestionService` → existing analysis workflow → `AIProvider` and PostgreSQL. `ConnectorAccountService` is shown off the HTTP path. Phase 11 workflow HTTP and Phase 12 execute sequences are documented in [`sequence-diagrams.md`](../architecture/sequence-diagrams.md), not in this `.mmd` file. |
| [`request-flow.mmd`](request-flow.mmd) | Sequence diagram of analyze: validation, identity TX, AI inference, history save, and failure paths including 503-before-AI |
| [`provider-abstraction.mmd`](provider-abstraction.mmd) | The `AIProvider` interface, `MockAIProvider`, `MicrosoftFoundryProvider`, `AmazonBedrockProvider`, and the configuration-driven factory |
| [`deployment-azure.mmd`](deployment-azure.mmd) | Azure Container Apps path: same image → ACR → Container Apps → user-assigned Managed Identity → Microsoft Foundry |
| [`deployment-aws.mmd`](deployment-aws.mmd) | ECS Fargate path: same image → ECR → Fargate → ECS container credential provider → Task Role → Amazon Bedrock |
| [`observability-application.mmd`](observability-application.mmd) | Common application telemetry: HTTP → request_id middleware → API → service → provider → structlog JSON → stdout |
| [`observability-azure.mmd`](observability-azure.mmd) | Azure observability: stdout JSON → Container Apps → Log Analytics, plus native Azure Monitor metrics (min 0 / max 1) |
| [`observability-aws.mmd`](observability-aws.mmd) | AWS observability: stdout JSON → awslogs → CloudWatch Logs, plus standard AWS/ECS CPU and memory (desiredCount 0 when idle) |
| [`identity.mmd`](identity.mmd) | Identity classes: Client → Entra → JWT → ECI; ECI → Foundry UAMI / Bedrock task role; GitHub → OIDC deploy identities; PostgreSQL identity future/not provisioned |
| [`cicd.mmd`](cicd.mmd) | GitHub Actions quality plus PostgreSQL integration; CD build-once → ACR → Azure Container Apps and ECR → ECS |
| [`ingress.mmd`](ingress.mmd) | Azure HTTPS → Container Apps → ECI; AWS current operator `/32` HTTP (verification-only); AWS ALB HTTPS verified then torn down |
| [`persistence.mmd`](persistence.mmd) | OIDC principal → IdentityResolver → users/external_identities → analysis workflow → AI provider and PostgreSQL history |
| [`persistence-cloud.mmd`](persistence-cloud.mmd) | Same ECI application; future Azure-local and AWS-local PostgreSQL not provisioned in Phase 9; CI ephemeral `postgres:16` proof |

## Implemented vs. Placeholder

`architecture.mmd`, `request-flow.mmd`, and `provider-abstraction.mmd` describe the analyze and connector paths as they exist today. `architecture.mmd` includes the Phase 10 connector path below the HTTP product surface. It does not depict workflow proposal/approval HTTP, the `CommunicationActionExecutor` write path, production OAuth, token storage, or background workers. Phase 11 and Phase 12 sequences live in [`sequence-diagrams.md`](../architecture/sequence-diagrams.md). The connector-to-workflow edges are the implemented composition path; they are not a claim that a live mailbox has been passed through Foundry or Bedrock.

`deployment-azure.mmd` and `deployment-aws.mmd` describe the Phase 6C hosting paths. Direct Fargate public-IP ingress is verification-only. See [`docs/cloud/deployment.md`](../cloud/deployment.md).

`observability-application.mmd`, `observability-azure.mmd`, and `observability-aws.mmd` describe the Phase 7 telemetry paths. See [`docs/cloud/observability.md`](../cloud/observability.md).

`identity.mmd`, `cicd.mmd`, and `ingress.mmd` describe Phase 8 identity, CI/CD, and ingress. Azure HTTPS and GitHub OIDC CD are live. AWS ALB HTTPS is verified-not-retained. AWS real-bearer traffic remains deferred until domain/ACM TLS. See [`docs/cloud/authentication.md`](../cloud/authentication.md) and [`docs/cloud/deployment.md`](../cloud/deployment.md).

`persistence.mmd` and `persistence-cloud.mmd` describe Phase 9 persistence. The application is PostgreSQL-compatible. Managed Azure/AWS databases are not provisioned. See [`docs/architecture/persistence.md`](../architecture/persistence.md) and [`docs/cloud/persistence.md`](../cloud/persistence.md).

## Embedding Mermaid in Markdown

GitHub, and most modern Markdown renderers, render Mermaid automatically inside a fenced code block tagged `mermaid`:

```mermaid
graph LR
    A[Client] --> B[FastAPI]
```

To embed one of the `.mmd` files in a document, copy its contents into a ```` ```mermaid ```` fenced block (Markdown does not support directly transcluding an external file). See [Sequence Diagrams](../architecture/sequence-diagrams.md) for worked examples using this pattern.
