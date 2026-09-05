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
| PostgreSQL persistence architecture | Implemented and CI-proven; Azure Flexible Server provisioned in 16B and used for 16C connector/workflow durability; Amazon RDS `eci-pg-dev` provisioned in 16D |
| Gmail delegated OAuth | Implemented; locally live-validated; AWS-hosted live-validated in 16E/16F including connect-another |
| Microsoft Graph delegated OAuth | Implemented; locally live-validated; Azure-hosted live-validated in 16C and 16F (connect-another / reactivation) |
| Azure Key Vault mailbox credential store | Implemented; live store-validated; Azure-hosted Graph credentials survived an ACA same-revision recycle in 16C |
| AWS Secrets Manager mailbox credential store | Implemented; live store-validated; selected as the ECS production backend in 16D; Gmail credential persistence exercised in 16E/16F |
| PostgreSQL advisory-lock credential coordination | Implemented and tested |
| Connected mailbox list / selected-message analyze | Implemented; locally live-validated with `MockAIProvider`; Azure Graph → Foundry in 16C/16F; AWS Gmail → Bedrock in 16E/16F |
| Phase 16 cloud-hosted browser topology | Frozen in 16A ([ADR-026](../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md)); 16A–16F completed. Current retained lineage `3fa3412` / schema `16f0001` / AWS task definition `eci-api-dev:8`. Compute scaled to zero; both managed databases Stopped. |

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

GitHub Actions CI/CD and GitHub OIDC deploy federation are implemented. Azure Key Vault and AWS Secrets Manager are Phase 13E mailbox OAuth credential stores; they are not `DATABASE_URL` secret backends. Phase 7 observability is implemented; tracing, custom metrics, dashboards, and alerts remain deferred. Phase 9 persistence is PostgreSQL-compatible and proven with ephemeral CI `postgres:16`. Phase 16B provisioned Azure Database for PostgreSQL Flexible Server `eci-pg-dev-susanta`. Phase 16D provisioned Amazon RDS `eci-pg-dev` (historical schema `13a0001`). Current schema head is `16f0001`. Current retained application lineage is `3fa3412` (AWS task definition `eci-api-dev:8`). Phase 16C live-validated Azure Graph → Foundry Analyze → Propose → Approve and stopped before Send. Phase 16D live-validated AWS HTTPS hosting only (historical image `0050b30` / `eci-api-dev:6`). Phase 16E certified AWS Gmail → Bedrock, including one historical Send. Phase 16F re-validated Azure Outlook connect-another → Foundry and AWS Gmail multi-account → Bedrock, both stopping before Send, then paused compute and both databases. Temporary database stop is not indefinite. See [Deployment](deployment.md), [PostgreSQL persistence](persistence.md), [Observability](observability.md), and [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md).
