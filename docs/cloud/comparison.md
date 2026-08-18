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
| Verification ingress | HTTPS + operator `/32` | task public IP:8000 + operator `/32` |
| Logging during deployment | Container Apps live logs (diagnostic) | CloudWatch `awslogs` |
| Retained application logs | Log Analytics `eci-law-dev` (30 days) | CloudWatch Logs `/ecs/eci-api-dev` (1 day) |
| Platform metrics | Container Apps native metrics | Standard AWS/ECS CPU and memory |
| Idle compute | min replicas 0 | desiredCount 0 |
| Static cloud credentials | None | None |

A production AWS service would normally introduce a stable ingress layer and TLS termination.

## Observability comparison (Phase 7)

Application telemetry is the same on both clouds: structlog JSON on stdout, `request_id` / `X-Request-ID`, `duration_ms`, and `error_class`. There is no application telemetry SDK beyond structlog. Tracing and custom metrics are deferred.

| Concern | Azure | AWS |
|---|---|---|
| Retained logs | Log Analytics | CloudWatch Logs via awslogs |
| Platform metrics | Container Apps native metrics | Standard AWS/ECS `CPUUtilization` / `MemoryUtilization` |
| Runtime cost control | min replicas 0 / max 1 | desiredCount 0 when idle |
| Not enabled | Application Insights, OpenTelemetry | Container Insights, ADOT, X-Ray |

See [Observability](observability.md).

See [Deployment](deployment.md).

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Amazon Bedrock](amazon-bedrock.md)
- [Authentication](authentication.md)
- [ADR-006](../decisions/ADR-006-azure-ai-foundry.md)
- [ADR-007](../decisions/ADR-007-amazon-bedrock.md)
- [ADR-008](../decisions/ADR-008-observability.md)
