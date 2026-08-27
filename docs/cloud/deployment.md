# Deployment

Phase 6C deploys one provider-independent Docker image to local Docker, Azure Container Apps, and Amazon ECS Fargate. Provider integration (Microsoft Foundry and Amazon Bedrock) is unchanged; hosting supplies environment variables and workload identity.

Phase 8 adds application-user OIDC, Azure managed HTTPS confirmation, AWS ALB verification then teardown, and GitHub Actions CI/CD with OIDC federation. Operator `/32` ingress restriction is network access control, not a substitute for API authentication. Production clouds use `AUTH_MODE=oidc`.

Phase 13 adds delegated mailbox OAuth and durable Azure Key Vault / AWS Secrets Manager credential stores in application code. Local Google/Microsoft consent and live store validation are recorded on the Phase 13 roadmap. Phase 14 adds bounded mailbox listing and selected-message analyze in application code; local-runtime live proof used real Entra OIDC, real Gmail/Graph mailboxes, local PostgreSQL, and `MockAIProvider`. Phase 16B redeployed ACA as current `master` with Azure PostgreSQL and Key Vault selected. Phase 16C live-certified the Azure Graph mailbox OAuth → Key Vault durability → Foundry analyze → Propose → Approve path on that runtime and stopped before Send. Phase 16D redeployed ECS as current `master` (`eci-api-dev:6`, image `0050b30`) behind CloudFront HTTPS → HTTP ALB, with Amazon RDS and Secrets Manager selected. That AWS path proved hosting, Entra/MSAL, CORS, persistence, and connector-list reads. It did not certify Gmail, Graph mailbox, Bedrock mailbox inference, or Send. Key Vault and Secrets Manager are mailbox OAuth backends, not `DATABASE_URL` injection. ECS supplies `DATABASE_URL` as a secret reference.

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

Runtime: `AI_PROVIDER=microsoft_foundry`, `APP_ENV=production`, `AUTH_MODE=oidc`.

Foundry remains in `rg-eci-dev`. Deployment resources are in `rg-eci-deploy-dev` (ACR `eciacrdev6c`, identity `eci-ca-identity-dev`, environment `eci-ca-env-dev`, app `eci-api-dev`, Log Analytics workspace `eci-law-dev`, SWA `eci-web-dev`, PostgreSQL `eci-pg-dev-susanta`, current image `eci-api:7518360`, revision `eci-api-dev--0000004`). Historical tags `dd55327`, `phase6c`, and `phase7a-5f4f5f8` remain in ACR.

Verified security controls:

- ACR admin authentication disabled
- image pull and Foundry access through the same user-assigned managed identity
- Key Vault secret get/set/delete through **Key Vault Secrets Officer** on that UAMI
- no Azure client secret, Foundry API key, or registry password
- external HTTPS ingress, `allowInsecure=false`, public (OIDC is access control; 16B removed operator `/32`)
- no Front Door, Application Gateway, or WAF
- min replicas 0, max replicas 1

Live analysis returned `provider=microsoft_foundry`. Phase 8D added one authorized analyze over HTTPS after a real Entra bearer token (Foundry calls = 1). Health and readiness returned HTTP 200. Phase 16B opened public HTTPS ingress (OIDC is access control). Phase 16C added one connected-mailbox Foundry inference on the same ACA runtime (`MicrosoftFoundryProvider`; `MockAIProvider` not used).

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

Runtime: `AI_PROVIDER=amazon_bedrock`, `APP_ENV=production`, `AUTH_MODE=oidc`, `BEDROCK_REGION=eu-south-2`, `BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0`. Current task definition is `eci-api-dev:6` (immutable image tag `0050b30`).

Default VPC reused for Fargate networking.

Phase 16D browser path (ADR-026):

```text
SPA CloudFront HTTPS (E1XFNK98P7PU2W)
→ private S3 origin through OAC (eci-spa-oac-dev)

API CloudFront HTTPS (E2IF9K4FM4A6WJ)
→ ALB HTTP:80 (eci-alb-dev)
→ ECS/Fargate :8000 (eci-api-dev:6)
→ Amazon RDS PostgreSQL (eci-pg-dev)
→ AWS Secrets Manager mailbox credential backend
```

SPA URL: `https://d1ut7j94w7lt3b.cloudfront.net`. API URL: `https://dnookm0ucbhv1.cloudfront.net`. Custom domain is not required. S3 is private; static website hosting is not used. CloudFront is the public HTTPS API boundary.

Verified security controls:

- Task Execution Role (`eci-ecs-execution-role-dev`) pulls from ECR, writes awslogs, and reads the `DATABASE_URL` secret reference (`eci-runtime-db-secret-execution-dev`)
- Application Task Role (`eci-bedrock-task-role-dev`) invokes Bedrock (`bedrock:InvokeModel`) and holds mailbox Secrets Manager data-plane permissions (`eci-mailbox-secrets-runtime-dev`; no `ListSecrets`)
- no static AWS keys, session tokens, or `AWS_PROFILE` in the container
- plaintext `DATABASE_URL` absent from task environment
- dedicated security group `eci-fargate-sg-dev` allows TCP 8000 from the ALB; ALB security group allows the CloudFront managed prefix list
- no NAT Gateway
- Phase 8B verified HTTPS domain/ACM → ALB → Fargate, then tore down that ALB for cost control; Phase 16D created a new HTTP ALB as the CloudFront origin

Earlier live analysis (Phase 6B/6C, before application-user OIDC) returned `provider=amazon_bedrock`. Health and readiness returned HTTP 200. Phase 8D did not invoke Bedrock: `AUTH_MODE=oidc` was live, missing-token analyze returned 401, and a fake unknown-kid JWT returned 401 (JWKS fail-closed). No real bearer token was sent over HTTP. Phase 16D accepted a real Entra bearer over CloudFront HTTPS for protected `GET /api/v1/analyses?limit=1` and `GET /api/v1/connector-accounts`. Bedrock was **not** invoked. Direct task-IP HTTP remains verification-only. Never send a real application-user bearer token over that HTTP path. ALB-native HTTPS still requires a custom domain and ACM (ADR-010). Phase 16 uses CloudFront default HTTPS in front of HTTP ALB instead. See [ADR-026](../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md) and [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md).

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

GitHub Actions Azure deploy identity `eci-github-deploy-dev` is a separate user-assigned managed identity. It has AcrPush and ACR Reader on `eciacrdev6c`, and Container Apps Contributor on `eci-api-dev` only. It does not have Foundry User.

AWS:

```text
boto3 standard credential chain
→ ECS container credential provider
→ ECS Task Role
→ bedrock:InvokeModel
```

AWS Task Execution Role is not the application identity. It only pulls images and writes logs. The application identity is the Task Role.

GitHub Actions AWS deploy identity `eci-github-deploy-dev` is a separate IAM role. It must not be `eci-developer`, `eci-bedrock-task-role-dev`, or `eci-ecs-execution-role-dev`.

Fargate credentials are not EC2 instance metadata.

Neither cloud path stores static cloud credentials in the image or in container configuration.

## GitHub Actions

Workflows:

- `.github/workflows/ci.yml` — pull_request and push to `master`; Python 3.12; `pip check`, `ruff`, `pytest`; plus job `PostgreSQL integration` with ephemeral `postgres:16`, Alembic upgrade/downgrade/upgrade, and 34 PostgreSQL tests; `contents: read` only
- `.github/workflows/deploy.yml` — `workflow_dispatch` with target `azure` | `aws` | `both`; build once; SHA and `stable` tags; concurrency group `eci-dev-deploy`

GitHub Environments:

| Environment | OIDC subject | Deploy identity |
|---|---|---|
| `azure` | `repo:Susanta2025-lab@238117232/enterprise-communication-intelligence@1320232309:environment:azure` | Azure user-assigned managed identity `eci-github-deploy-dev` |
| `aws` | `repo:Susanta2025-lab@238117232/enterprise-communication-intelligence@1320232309:environment:aws` | AWS IAM role `eci-github-deploy-dev` |

Required non-secret environment variables (no passwords or access keys):

Azure environment: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP` (`rg-eci-deploy-dev`), `AZURE_ACR_NAME` (`eciacrdev6c`), `AZURE_CONTAINER_APP_NAME` (`eci-api-dev`)

AWS environment: `AWS_REGION` (`eu-south-2`), `AWS_ROLE_ARN`, `AWS_ECR_REPOSITORY` (`eci-api-dev`), `AWS_ECS_CLUSTER` (`eci-cluster-dev`), `AWS_ECS_SERVICE` (`eci-api-dev`), `AWS_CONTAINER_NAME` (`eci-api`)

`AZURE_CLIENT_ID` is the client ID of Azure user-assigned managed identity `eci-github-deploy-dev`. `AWS_ROLE_ARN` is the ARN of IAM role `eci-github-deploy-dev`.

GitHub Environments `azure` and `aws` exist with the non-secret identifier variables listed above. Do not store Azure client secrets or AWS access keys in GitHub.

Phase 8D executed Deploy after live `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL` were configured. Run `dd55327` used `target=both`. GitHub OIDC token exchange succeeded on Azure and AWS. The workflow built once and tagged `dd55327` and `stable`. ACR and ECR received the same digest `sha256:0590bf6f7b2ae5614dd35af0307763cb0303e98948531bab2352258e6773ed70`. Azure currently runs `eci-api:7518360` (Phase 16B). AWS currently uses task definition `eci-api-dev:6` (Phase 16D; image `0050b30`). CD remains `workflow_dispatch` only. Azure frontend SWA deploy is an optional dispatch input.

Phase 9C verified PostgreSQL on GitHub Actions run `32336909759` (Lint and test success; PostgreSQL integration success; 34 tests; Alembic round-trip to revision `9a0001`). That job does not deploy and does not use a managed cloud database. Phase 9D does not run `deploy.yml`. Azure now has Flexible Server `DATABASE_URL` (16B). AWS now has RDS `DATABASE_URL` as an ECS secret reference (16D).

### AWS GitHub OIDC (created)

An IAM administrator created the GitHub OIDC provider and role `eci-github-deploy-dev`. Creation is complete. `eci-developer` still cannot inspect those IAM objects (`iam:GetOpenIDConnectProvider`, `iam:GetRole`, `iam:GetRolePolicy` denied). Operator-attested trust:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:Susanta2025-lab@238117232/enterprise-communication-intelligence@1320232309:environment:aws"
        }
      }
    }
  ]
}
```

Intended inline policy `ECIPhase8CDeploymentPolicy`: ECR authorization token (`Resource=*`, unavoidable); ECR push/read on repository `eci-api-dev`; ECS describe/update on `eci-cluster-dev` / `eci-api-dev`; `ecs:RegisterTaskDefinition` and `ecs:DescribeTaskDefinition`; `iam:PassRole` only for `eci-ecs-execution-role-dev` and `eci-bedrock-task-role-dev` with `iam:PassedToService=ecs-tasks.amazonaws.com`. Do not grant `bedrock:InvokeModel`, `AdministratorAccess`, or IAM role-creation APIs.

GitHub Environment `aws` variable `AWS_ROLE_ARN` points at that role. CD describes the current task definition, strips response-only fields, and registers a new revision with only the application image changed.

## Security (verified)

Common:

- one provider-independent image
- non-root container runtime
- no `.env` in the image
- no static cloud credentials baked into the image
- cloud identity resolved at runtime

Azure: ACR admin disabled; managed-identity pull and Foundry authentication; public HTTPS ingress with `allowInsecure=false` (OIDC is access control).

AWS: dedicated ECI security groups; CloudFront HTTPS browser edge; ALB HTTP origin restricted to the CloudFront prefix list; Fargate TCP 8000 from the ALB; separate execution and task roles; least-privilege Bedrock `InvokeModel` plus mailbox Secrets Manager data-plane on the task role; `DATABASE_URL` via ECS secret reference; no NAT; no static AWS credentials.

Application-user JWT authentication is live at the API boundary (`AUTH_MODE=oidc`). Azure accepted a real bearer token over HTTPS. Phase 16D accepted a real bearer token over AWS CloudFront HTTPS. Never send a real bearer token over AWS task-IP HTTP.

## Ingress

Azure live: Container Apps HTTPS → ECI.

AWS live (16D): CloudFront HTTPS → HTTP ALB → ECS. Direct task-IP HTTP remains verification-only.

AWS verified, not retained (Phase 8B): HTTPS domain + ACM → ALB → ECS. Recreating that ALB-native TLS path still requires a custom domain and ACM certificate (ADR-010).

## Phase 8D verification

| Capability | Azure | AWS |
|---|---|---|
| Application image deployment | verified | verified |
| GitHub OIDC deployment | verified | verified |
| Workload identity | verified | verified |
| Public health | verified HTTPS | verified controlled HTTP |
| Missing-token auth | verified | verified |
| JWKS/OIDC runtime | verified | verified (fake unknown-kid 401; no real bearer) |
| Real bearer authorized request | verified | verified over CloudFront HTTPS in 16D (analyses + connector-list; no Bedrock) |
| AI inference after auth | Foundry verified once | deferred until 16E mailbox → Bedrock |
| Production TLS | ACA managed TLS | CloudFront default HTTPS (no custom domain) |

## Cost controls

Azure: ACR Basic; Container Apps Consumption; min replicas 0; max replicas 1; Log Analytics 30-day retention; no Application Insights; no custom metrics; no dashboards/alerts. ACR Basic and Log Analytics ingestion/retention can incur charges.

AWS: one Fargate task 0.5 vCPU / 1 GiB during 16D (`desiredCount=1`); ALB standing hourly cost while retained; RDS `eci-pg-dev` material; CloudFront/S3 usage; CloudWatch Logs retention 1 day; Container Insights disabled. Retained ECR image storage and CloudWatch Logs storage/usage may incur charges. Scale-to-zero and optional ALB teardown remain 16F.

This is not a zero-cost deployment.

## Observability

Phase 7 is implemented. The same image writes structured JSON to stdout on both clouds.

Azure: Container Apps environment `eci-ca-env-dev` sends logs to Log Analytics workspace `eci-law-dev` (30 days). Native Container Apps metrics (`Requests`, `ResponseTime`, `Replicas`, `CpuPercentage`, `MemoryPercentage`, `RestartCount`) were verified. Use Log Analytics for historical inspection. `az containerapp logs show` can wake a scale-to-zero replica and is for active diagnostics only.

AWS: current task definition is `eci-api-dev:6` (`0050b30`). CloudWatch log group `/ecs/eci-api-dev` retains logs for 1 day via awslogs. Standard AWS/ECS `CPUUtilization` and `MemoryUtilization` were verified in Phase 7. Container Insights remains disabled. 16D left the service at `desiredCount=1` for the live environment; scale-to-zero remains 16F.

Phase 7 does not include distributed tracing, custom metrics, alerts, dashboards, or a full production SRE/SLO stack.

See [Observability](observability.md).

## CI/CD

See [GitHub Actions](#github-actions).

## Not implemented

- Azure App Service / AWS App Runner (not used; hosting is Container Apps and ECS Fargate)
- Azure Monitor / Amazon CloudWatch tracing, dashboards, and custom metrics (native log retention and platform metrics are in Phase 7)
- AWS persistent HTTPS / custom domain (ALB-native TLS still needs ACM/domain; Phase 16D uses CloudFront default HTTPS instead)
- automatic (push/tag) cloud deployment
- Phase 8B temporary IAM policy cleanup (`ECIPhase8BIngressVerificationPolicy`), if still attached — IAM-admin follow-up
- Phase 16D temporary operator IAM cleanup — deferred to 16F
- Key Vault / Secrets Manager injection of `DATABASE_URL` as an application mailbox-store feature (ECS supplies `DATABASE_URL` as a platform secret reference)
- Entra or RDS IAM database authentication
- automatic schema migration from application startup or from every replica

See [Cloud Roadmap](roadmap.md), [Authentication](authentication.md), and [Provider comparison](comparison.md).
