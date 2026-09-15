# Cloud Integration

ECI Platform keeps cloud AI SDKs behind the `AIProvider` interface. Application and API code never import vendor clients.

The same cloud-neutral application/domain/API deploys independently to Azure and AWS. **There is no cross-cloud database replication**—each cloud has its own PostgreSQL and cloud resources.

## Current status

| Capability | Status |
|---|---|
| Mock provider | Implemented (`AI_PROVIDER=mock`) |
| Microsoft Foundry provider | Implemented (`AI_PROVIDER=microsoft_foundry`); model GPT-5.4-mini |
| Amazon Bedrock provider | Implemented and live-verified (`AI_PROVIDER=amazon_bedrock`); model Claude Haiku 4.5 |
| Azure application hosting | Implemented (Static Web Apps → Container Apps → PostgreSQL Flexible Server → Foundry); Spain Central |
| AWS application hosting | Implemented (S3/CloudFront → CloudFront API → ALB → ECS Fargate → RDS → Bedrock); eu-south-2 |
| Application telemetry | Implemented (structlog JSON, `request_id`, `duration_ms`) |
| Azure retained logs / native metrics | Implemented (Log Analytics + Container Apps metrics) |
| AWS retained logs / standard ECS metrics | Implemented (CloudWatch Logs + AWS/ECS CPU/memory) |
| Application-user OIDC JWT | Implemented (`AUTH_MODE=oidc`; live product login is Microsoft Entra External ID) |
| Application RBAC (Phase 19) | Implemented: persisted `application_role` (`user` \| `owner`); `require_owner`; `/api/v1/me`; owner-only `/api/v1/admin/ping`; bootstrap CLI |
| Owner deployment indicator | Presentation-only Azure/AWS badge for authenticated Platform Owners (not authorization) |
| GitHub Actions CI/CD | Implemented (automatic tests-only CI; manual `workflow_dispatch` CD) |
| GitHub OIDC deploy federation | Implemented (Azure UAMI and AWS IAM role `eci-github-deploy-dev`) |
| PostgreSQL persistence | Implemented; separate managed DB per cloud (Azure Flexible Server; Amazon RDS); schema head `19b0001` |
| Gmail delegated OAuth | Implemented; locally live-validated; AWS-hosted live-validated in 16E/16F and Phase 18 |
| Microsoft Graph delegated OAuth | Implemented; locally live-validated; Azure-hosted live-validated in 16C/16F and Phase 18 attachment path |
| Azure Key Vault mailbox credential store | Implemented; live store-validated; Azure-hosted Graph credentials survived an ACA same-revision recycle in 16C |
| AWS Secrets Manager mailbox credential store | Implemented; live store-validated; selected as the ECS production backend in 16D; Gmail credential persistence exercised in 16E/16F/18 |
| PostgreSQL advisory-lock credential coordination | Implemented and tested |
| Connected mailbox list / selected-message analyze | Implemented; locally live-validated with `MockAIProvider`; Azure Graph → Foundry in 16C/16F; AWS Gmail → Bedrock in 16E/16F |
| Secure attachment intelligence | Implemented (Phase 18 CLOSED / PASS): metadata-only listing; explicit Analyze; ClamAV before parse/AI; PDF/DOCX live-validated on crossed Azure Outlook→Foundry and AWS Gmail→Bedrock paths; XLSX/JPEG/PNG fail-closed or capability-gated; no Send in Phase 18 |
| Phase 16 cloud-hosted browser topology | Frozen in 16A ([ADR-026](../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md)); 16A–16F completed. Current schema head: `19b0001`. Cost-aware idle posture may scale compute to zero and stop managed databases. |

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Amazon Bedrock](amazon-bedrock.md)
- [Authentication](authentication.md)
- [Provider comparison](comparison.md)
- [Cloud roadmap](roadmap.md)
- [Deployment](deployment.md)
- [Observability](observability.md)
- [PostgreSQL persistence](persistence.md)

## Identity domains (do not conflate)

```text
ECI application login     Microsoft Entra External ID → OIDC JWT → users.id → application_role
Mailbox login             Gmail / Microsoft Graph delegated OAuth → credential store
Cloud workload identity   Azure Managed Identity / AWS ECS Task Role
Deploy identity           GitHub OIDC → Azure UAMI / AWS IAM deploy role
```

Signing into ECI does not grant mailbox access. Mailbox OAuth does not determine Platform Owner. Owner authorization uses verified `(issuer, subject)` mapping—not email.

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

Provider-specific adapters remain behind the shared application-facing contract. Do not imply Foundry and Bedrock are interchangeable at the infrastructure level. Do not treat Azure vs AWS AI latency as a pure cloud-performance comparison—model/provider differences also matter.

## Deployment (implemented)

One Docker image runs locally with mock, on Azure Container Apps with Foundry, and on ECS Fargate with Bedrock. Hosting uses workload identity, not static cloud keys. Azure App Service and AWS App Runner are not used.

GitHub Actions CI/CD and GitHub OIDC deploy federation are implemented. Azure Key Vault and AWS Secrets Manager are Phase 13E mailbox OAuth credential stores; they are not `DATABASE_URL` secret backends. Phase 7 observability is implemented; tracing, custom metrics, dashboards, and alerts remain deferred. Phase 9 persistence is PostgreSQL-compatible and proven with ephemeral CI `postgres:16`. Phase 16 provisioned colocated managed databases per cloud. Current schema head is `19b0001`. Cost-aware idle posture may scale compute to zero and stop managed databases—restart is required for meaningful live testing.

Technical cloud validation includes application identity and Platform Owner activation on AWS and Azure (presentation indicator included). That is technical validation only—**Phase 17D external business-user verification remains deferred**.

See [Deployment](deployment.md), [PostgreSQL persistence](persistence.md), [Observability](observability.md), [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md), [Phase 18](../roadmap/phase-18-secure-attachment-intelligence.md), and [Phase 19](../roadmap/phase-19-platform-owner-identity-and-application-rbac.md).
