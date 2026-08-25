# Cloud Provider Comparison

ECI compares Microsoft Foundry and Amazon Bedrock behind the same domain `AIProvider` contract. The comparison is architectural, not a claim that one cloud is universally better.

The application, domain, and REST API do not change when the configured provider changes. Both real LLM adapters reuse `app/providers/common/` for the ECI communication-analysis contract (prompt, structured output model, JSON validation, domain mapping, and request flags). Cloud SDKs and schema envelopes stay provider-specific.

| Dimension | Microsoft Foundry | Amazon Bedrock |
|---|---|---|
| ECI provider | `MicrosoftFoundryProvider` | `AmazonBedrockProvider` |
| Configuration name | `microsoft_foundry` | `amazon_bedrock` |
| Initial model | GPT-5.4-mini | Claude Haiku 4.5 |
| SDK | Azure AI Projects / OpenAI client | boto3 |
| API style | Responses API | Converse |
| Structured output | OpenAI-style strict JSON Schema | `outputConfig.textFormat` JSON Schema |
| Local auth | `DefaultAzureCredential` → Azure CLI | boto3 chain → `aws login` credentials |
| Deployed auth | `DefaultAzureCredential` → user-assigned Managed Identity | boto3 → ECS container credential provider → ECS Task Role |
| Region used | Spain Central | `eu-south-2` |
| Shared ECI contract | `providers/common` | `providers/common` |
| Implementation status | Implemented and live-verified through ECI | Implemented and live-verified through ECI |

Neither adapter stores static cloud keys in application Settings.

`MockAIProvider` remains a deterministic offline path and does not use the shared LLM serialization layer.

## Hosting comparison (Phase 6C)

The same Docker image was verified locally and deployed to both clouds. Direct Fargate public-IP access is a deliberately minimal verification design, not recommended production ingress. Operator `/32` restriction is network access control, not application-user authentication.

| Concern | Azure | AWS |
|---|---|---|
| Container Registry | Azure Container Registry | Amazon ECR |
| Container Runtime | Azure Container Apps | ECS Fargate |
| Application Identity | User-Assigned Managed Identity | ECS Task Role |
| SDK Credential Resolution | `DefaultAzureCredential` | boto3 credential chain |
| AI Platform | Microsoft Foundry | Amazon Bedrock |
| Model | GPT-5.4-mini deployment | Claude Haiku 4.5 |
| Runtime scaling | min 0 / max 1 | service scaled to `desiredCount` 0 after verification |
| Verification ingress | HTTPS public (OIDC; 16B) | task public IP:8000 + operator `/32` |
| Logging during deployment | Container Apps live logs (diagnostic) | CloudWatch `awslogs` |
| Retained application logs | Log Analytics `eci-law-dev` (30 days) | CloudWatch Logs `/ecs/eci-api-dev` (1 day) |
| Platform metrics | Container Apps native metrics | Standard AWS/ECS CPU and memory |
| Idle compute | min replicas 0 | desiredCount 0 |
| Static cloud credentials | None | None |

A production AWS service would normally introduce a stable ingress layer and TLS termination.

## Production hardening (Phase 8)

Application-user OIDC is live on both clouds (`AUTH_MODE=oidc`). Azure accepted a real bearer token over managed HTTPS. AWS missing-token and JWKS fail-closed paths were verified over operator `/32` HTTP. A real bearer token must not be sent over that HTTP path.

GitHub Actions CI is automatic and tests-only. Manual `workflow_dispatch` CD deploys `azure` | `aws` | `both` with one build. GitHub OIDC federates to Azure user-assigned managed identity `eci-github-deploy-dev` and AWS IAM role `eci-github-deploy-dev`. Those deploy identities are not the runtime Foundry or Bedrock identities.

| Concern | Azure | AWS |
|---|---|---|
| Application-user auth | Entra JWT over HTTPS | Entra JWT configured; real bearer deferred until TLS |
| Live ingress | Container Apps HTTPS, public (OIDC) | operator `/32` HTTP (verification-only) |
| Production TLS | ACA managed TLS | domain/ACM deferred |
| Deploy identity | user-assigned managed identity `eci-github-deploy-dev` | IAM role `eci-github-deploy-dev` |
| Workload identity | user-assigned managed identity `eci-ca-identity-dev` | Task Role `eci-bedrock-task-role-dev` |

See [Authentication](authentication.md), [Deployment](deployment.md), [PostgreSQL persistence](persistence.md), [ADR-009](../decisions/ADR-009-application-user-authentication.md), [ADR-010](../decisions/ADR-010-multi-cloud-ingress.md), [ADR-011](../decisions/ADR-011-github-actions-oidc-cicd.md), [ADR-012](../decisions/ADR-012-postgresql-persistence-architecture.md), [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md), and [ADR-014](../decisions/ADR-014-cloud-postgresql-deployment-strategy.md).

## Observability comparison (Phase 7)

Application telemetry is the same on both clouds: structlog JSON on stdout, `request_id` / `X-Request-ID`, `duration_ms`, and `error_class`. There is no application telemetry SDK beyond structlog. Tracing and custom metrics are deferred.

| Concern | Azure | AWS |
|---|---|---|
| Retained logs | Log Analytics | CloudWatch Logs via awslogs |
| Platform metrics | Container Apps native metrics | Standard AWS/ECS `CPUUtilization` / `MemoryUtilization` |
| Runtime cost control | min replicas 0 / max 1 | desiredCount 0 when idle |
| Not enabled | Application Insights, OpenTelemetry | Container Insights, ADOT, X-Ray |

See [Observability](observability.md).

## Persistence comparison (Phase 9)

The persistence implementation is the same on both clouds: PostgreSQL via SQLAlchemy, Alembic, and `DATABASE_URL`. Phase 9 does not provision a managed database in either cloud and does not replicate data across clouds.

| Concern | Azure | AWS |
|---|---|---|
| Production dialect | PostgreSQL | PostgreSQL |
| Managed database | Azure PostgreSQL Flexible Server `eci-pg-dev-susanta` (16B) | not provisioned (16D) |
| Preferred future colocated DB | Azure Database for PostgreSQL Flexible Server | Amazon RDS for PostgreSQL |
| Phase 9 proof | GitHub Actions `postgres:16` | GitHub Actions `postgres:16` |

See [PostgreSQL persistence](persistence.md).

See [Deployment](deployment.md).

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Amazon Bedrock](amazon-bedrock.md)
- [Authentication](authentication.md)
- [ADR-006](../decisions/ADR-006-azure-ai-foundry.md)
- [ADR-007](../decisions/ADR-007-amazon-bedrock.md)
- [ADR-008](../decisions/ADR-008-observability.md)
