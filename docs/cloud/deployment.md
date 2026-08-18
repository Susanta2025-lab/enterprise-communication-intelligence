# Deployment

Phase 6C deploys one provider-independent Docker image to local Docker, Azure Container Apps, and Amazon ECS Fargate. Provider integration (Microsoft Foundry and Amazon Bedrock) is unchanged; hosting supplies environment variables and workload identity.

This is a verified deployment foundation, not a fully production-hardened platform. Application-user JWT authentication is implemented in the API; live cloud identity-provider registration is not part of Phase 8A. Operator `/32` ingress restriction is network access control, not a substitute for API authentication.

## Same image

```text
same ECI Docker image
├── local Docker / mock
├── Azure Container Apps / Foundry
└── ECS Fargate / Bedrock
```

The image was verified locally (`enterprise-communication-intelligence-eci:latest`) and pushed to both clouds without rebuild. Cloud differences are configuration and identity, not a second Dockerfile.

Local Compose binds `8000:8000` with `AI_PROVIDER=mock` and `APP_ENV=production`. It does not mount source or inject cloud credentials.

## Request paths

Local:

```text
REST API
→ CommunicationAnalysisService
→ AIProvider
→ MockAIProvider
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

## Azure (implemented)

```text
ECI Docker image
→ Azure Container Registry
→ Azure Container Apps
→ User-Assigned Managed Identity
→ DefaultAzureCredential
→ Foundry User
→ Microsoft Foundry
→ eci-gpt-54-mini
```

Runtime: `AI_PROVIDER=microsoft_foundry`, `APP_ENV=production`.

Foundry remains in `rg-eci-dev`. Deployment resources are in `rg-eci-deploy-dev` (ACR `eciacrdev6c`, identity `eci-ca-identity-dev`, environment `eci-ca-env-dev`, app `eci-api-dev`, Log Analytics workspace `eci-law-dev`, current image `eci-api:phase7a-5f4f5f8`, revision `eci-api-dev--0000001`). The earlier `phase6c` tag remains in ACR.

Verified security controls:

- ACR admin authentication disabled
- image pull and Foundry access through the same user-assigned managed identity
- no Azure client secret, Foundry API key, or registry password
- external HTTPS ingress restricted to operator `/32`
- min replicas 0, max replicas 1

Live analysis returned `provider=microsoft_foundry`. Health and readiness returned HTTP 200. The Azure app remains deployed with restricted ingress.

Do not publish the operator IP, subscription ID, tenant ID, principal ID, identity client ID, or complete Azure resource IDs.

Operator commands: [Azure Container Apps runbook](../../deployment/azure/README.md).

## AWS (implemented)

```text
ECI Docker image
→ Amazon ECR
→ Amazon ECS
→ AWS Fargate
→ ECS Task Role
→ boto3 standard credential chain
→ ECS container credential provider
→ Amazon Bedrock Runtime
→ Converse
→ EU Claude Haiku 4.5 inference profile
```

Runtime: `AI_PROVIDER=amazon_bedrock`, `APP_ENV=production`, `BEDROCK_REGION=eu-south-2`, `BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0`.

Default VPC reused for Fargate networking; not modified.

Verified security controls:

- Task Execution Role (`eci-ecs-execution-role-dev`) pulls from ECR and writes awslogs
- Application Task Role (`eci-bedrock-task-role-dev`) invokes Bedrock only (`bedrock:InvokeModel`)
- no static AWS keys, session tokens, or `AWS_PROFILE` in the container
- dedicated security group `eci-fargate-sg-dev` allows TCP 8000 from operator `/32` only
- no NAT Gateway and no ALB/NLB for Phase 6C verification

Live analysis returned `provider=amazon_bedrock`. Health and readiness returned HTTP 200. After verification the ECS service was scaled to `desiredCount=0`. Direct task-IP access is a deliberately minimal Phase 6C verification design; a production service would normally introduce a stable ingress layer and TLS termination.

Do not publish AWS account ID, role ARNs, VPC IDs, subnet IDs, security-group IDs, ENI IDs, task ARNs, or public IPs.

Operator commands: [AWS ECS Fargate runbook](../../deployment/aws/README.md).

## Identity

Azure:

```text
DefaultAzureCredential
→ AZURE_CLIENT_ID selects user-assigned Managed Identity
→ Foundry User
→ Microsoft Foundry
```

AWS:

```text
boto3 standard credential chain
→ ECS container credential provider
→ ECS Task Role
→ bedrock:InvokeModel
```

AWS Task Execution Role is not the application identity. It only pulls images and writes logs. The application identity is the Task Role.

Fargate credentials are not EC2 instance metadata.

Neither cloud path stores static cloud credentials in the image or in container configuration.

## Security (verified)

Common:

- one provider-independent image
- non-root container runtime
- no `.env` in the image
- no static cloud credentials baked into the image
- cloud identity resolved at runtime

Azure: ACR admin disabled; managed-identity pull and Foundry authentication; operator `/32` HTTPS ingress.

AWS: dedicated ECI security group; operator `/32` on TCP 8000; no `0.0.0.0/0` inbound on 8000; separate execution and task roles; least-privilege Bedrock `InvokeModel`; no NAT or load balancer for this verification.

Application-user JWT authentication is implemented at the API boundary. Live issuer registration remains a later configuration step.

## Cost controls

Azure: ACR Basic; Container Apps Consumption; min replicas 0; max replicas 1; Log Analytics 30-day retention; no Application Insights; no custom metrics; no dashboards/alerts. ACR Basic and Log Analytics ingestion/retention can incur charges.

AWS: one temporary 0.5 vCPU / 1 GiB Fargate task during verification; service returned to `desiredCount=0`, so Fargate compute is not running; no NAT Gateway; no ALB/NLB; CloudWatch Logs retention 1 day; Container Insights disabled. Retained ECR image storage and CloudWatch Logs storage/usage may incur charges.

This is not a zero-cost deployment.

## Observability

Phase 7 is implemented. The same Phase 7A image writes structured JSON to stdout on both clouds.

Azure: Container Apps environment `eci-ca-env-dev` sends logs to Log Analytics workspace `eci-law-dev` (30 days). Native Container Apps metrics (`Requests`, `ResponseTime`, `Replicas`, `CpuPercentage`, `MemoryPercentage`, `RestartCount`) were verified. Use Log Analytics for historical inspection. `az containerapp logs show` can wake a scale-to-zero replica and is for active diagnostics only.

AWS: current task definition is `eci-api-dev:2` (`phase7a-5f4f5f8`). CloudWatch log group `/ecs/eci-api-dev` retains logs for 1 day via awslogs. Standard AWS/ECS `CPUUtilization` and `MemoryUtilization` were verified. Container Insights remains disabled. The service stays at `desiredCount=0` when idle.

Phase 7 does not include distributed tracing, custom metrics, alerts, dashboards, or a full production SRE/SLO stack.

See [Observability](observability.md).

## CI/CD

CI/CD automation is intentionally deferred until the manually validated Azure and AWS deployment paths are stable. GitHub Actions is not implemented.

## Not implemented

- Azure App Service / AWS App Runner (not used; hosting is Container Apps and ECS Fargate)
- Azure Key Vault / AWS Secrets Manager
- Azure Monitor / Amazon CloudWatch tracing, dashboards, and custom metrics (native log retention and platform metrics are in Phase 7)
- production networking beyond operator-restricted verification ingress
- CI/CD deployment pipelines

See [Cloud Roadmap](roadmap.md), [Authentication](authentication.md), and [Provider comparison](comparison.md).
