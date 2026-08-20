# Cloud Integration

ECI Platform keeps cloud AI SDKs behind the `AIProvider` interface. Application and API code never import vendor clients.

## Current status

| Capability | Status |
|---|---|
| Mock provider | Implemented (`AI_PROVIDER=mock`) |
| Microsoft Foundry provider | Implemented (`AI_PROVIDER=microsoft_foundry`) |
| Amazon Bedrock provider | Implemented and live-verified (`AI_PROVIDER=amazon_bedrock`) |
| Azure application hosting | Implemented (Container Apps + user-assigned Managed Identity) |
| AWS application hosting | Implemented (ECS Fargate + ECS Task Role) |
| Application telemetry | Implemented (structlog JSON, `request_id`, `duration_ms`) |
| Azure retained logs / native metrics | Implemented (Log Analytics + Container Apps metrics) |
| AWS retained logs / standard ECS metrics | Implemented (CloudWatch Logs + AWS/ECS CPU/memory) |
| Application-user OIDC JWT | Implemented (`AUTH_MODE=oidc`; live Entra is the first IdP) |
| GitHub Actions CI/CD | Implemented (automatic tests-only CI; manual `workflow_dispatch` CD) |
| GitHub OIDC deploy federation | Implemented (Azure UAMI and AWS IAM role `eci-github-deploy-dev`) |
| PostgreSQL persistence architecture | Implemented and CI-proven; no managed cloud database provisioned |

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Amazon Bedrock](amazon-bedrock.md)
- [Authentication](authentication.md)
- [Provider comparison](comparison.md)
- [Cloud roadmap](roadmap.md)
- [Deployment](deployment.md)
- [Observability](observability.md)
- [PostgreSQL persistence](persistence.md)

## Microsoft Foundry (implemented)

`MicrosoftFoundryProvider` in `app/providers/microsoft_foundry/` uses:

```text
DefaultAzureCredential
        ↓
AIProjectClient
        ↓
get_openai_client()
        ↓
responses.create(...)
```

Verified development infrastructure (no subscription IDs, tenant IDs, or secrets):

| Item | Value |
|---|---|
| Subscription | ECI-Development |
| Resource group | rg-eci-dev |
| Region | Spain Central |
| Foundry resource | eci-foundry-dev-susanta |
| Foundry project | eci-project-dev |
| Deployment | eci-gpt-54-mini |
| Model | gpt-5.4-mini |
| Version | 2026-03-17 |
| Deployment type | DataZoneStandard |

## Amazon Bedrock (implemented and live-verified)

`AmazonBedrockProvider` in `app/providers/amazon_bedrock/` uses:

```text
boto3 standard credential chain
        ↓
bedrock-runtime
        ↓
converse(...)
        ↓
outputConfig.textFormat JSON Schema
```

Current configurable baseline:

| Item | Value |
|---|---|
| Region | `eu-south-2` (Europe / Spain) |
| Initial model | Claude Haiku 4.5 |
| Model ID | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` |

Independent CLI Bedrock capability was verified before implementation. Offline automated tests are complete. The real ECI REST path to Bedrock has been live-verified.

## Shared LLM analysis contract

Microsoft Foundry and Amazon Bedrock share `app/providers/common/` for ECI prompt construction, structured-output models, JSON validation, and domain mapping. That package is not a generic LLM framework. `MockAIProvider` does not use it.

## Deployment (implemented)

One Docker image runs locally with mock, on Azure Container Apps with Foundry, and on ECS Fargate with Bedrock. Hosting uses workload identity, not static cloud keys. Azure App Service and AWS App Runner are not used.

GitHub Actions CI/CD and GitHub OIDC deploy federation are implemented. Key Vault and Secrets Manager remain later work. Phase 7 observability is implemented; tracing, custom metrics, dashboards, and alerts remain deferred. Phase 9 persistence is PostgreSQL-compatible and proven with ephemeral CI `postgres:16`; Azure Database for PostgreSQL and Amazon RDS are not provisioned. See [Deployment](deployment.md), [PostgreSQL persistence](persistence.md), and [Observability](observability.md).
