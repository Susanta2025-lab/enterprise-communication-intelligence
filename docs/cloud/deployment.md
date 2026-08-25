# Deployment

Phase 6C deploys one provider-independent Docker image to local Docker, Azure Container Apps, and Amazon ECS Fargate. Provider integration (Microsoft Foundry and Amazon Bedrock) is unchanged; hosting supplies environment variables and workload identity.

Phase 8 adds application-user OIDC, Azure managed HTTPS confirmation, AWS ALB verification then teardown, and GitHub Actions CI/CD with OIDC federation. Operator `/32` ingress restriction is network access control, not a substitute for API authentication. Production clouds use `AUTH_MODE=oidc`.

Phase 13 adds delegated mailbox OAuth and durable Azure Key Vault / AWS Secrets Manager credential stores in application code. Local Google/Microsoft consent and live store validation are recorded on the Phase 13 roadmap. Phase 14 adds bounded mailbox listing and selected-message analyze in application code; local-runtime live proof used real Entra OIDC, real Gmail/Graph mailboxes, local PostgreSQL, and `MockAIProvider`. The retained Container App and ECS service have not been redeployed or certified as a complete Phase 13 mailbox-OAuth runtime or a Phase 14 mailbox→AI runtime. That local proof did not call Foundry or Bedrock. Key Vault and Secrets Manager are mailbox OAuth backends, not `DATABASE_URL` injection.

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

Foundry remains in `rg-eci-dev`. Deployment resources are in `rg-eci-deploy-dev` (ACR `eciacrdev6c`, identity `eci-ca-identity-dev`, environment `eci-ca-env-dev`, app `eci-api-dev`, Log Analytics workspace `eci-law-dev`, current image `eci-api:dd55327`). The earlier `phase6c` and `phase7a-5f4f5f8` tags remain in ACR.

Verified security controls:

- ACR admin authentication disabled
- image pull and Foundry access through the same user-assigned managed identity
- no Azure client secret, Foundry API key, or registry password
- external HTTPS ingress restricted to operator `/32`, `allowInsecure=false` (Phase 16A inventory confirmed; 16B must change this for browser/OAuth proof)
- no Front Door, Application Gateway, or WAF
- min replicas 0, max replicas 1

Live analysis returned `provider=microsoft_foundry`. Phase 8D added one authorized analyze over HTTPS after a real Entra bearer token (Foundry calls = 1). Health and readiness returned HTTP 200. The Azure app remains deployed with restricted ingress.

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

Runtime: `AI_PROVIDER=amazon_bedrock`, `APP_ENV=production`, `AUTH_MODE=oidc`, `BEDROCK_REGION=eu-south-2`, `BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0`. Current task definition is `eci-api-dev:4`.

Default VPC reused for Fargate networking; not modified.

Verified security controls:

- Task Execution Role (`eci-ecs-execution-role-dev`) pulls from ECR and writes awslogs
- Application Task Role (`eci-bedrock-task-role-dev`) invokes Bedrock only (`bedrock:InvokeModel`)
- no static AWS keys, session tokens, or `AWS_PROFILE` in the container
- dedicated security group `eci-fargate-sg-dev` allows TCP 8000 from operator `/32` only
- no NAT Gateway
- Phase 8B verified HTTPS domain/ACM → ALB → Fargate, then tore down the ALB for cost control

Earlier live analysis (Phase 6B/6C, before application-user OIDC) returned `provider=amazon_bedrock`. Health and readiness returned HTTP 200. Phase 8D did not invoke Bedrock: `AUTH_MODE=oidc` was live, missing-token analyze returned 401, and a fake unknown-kid JWT returned 401 (JWKS fail-closed). No real bearer token was sent over HTTP. After verification the ECS service was scaled to `desiredCount=0`. Direct task-IP HTTP is verification-only. Never send a real application-user bearer token over that HTTP path. ALB-native HTTPS still requires a custom domain and ACM (ADR-010). Phase 16A freezes a different AWS API path that does **not** need a custom domain: CloudFront default HTTPS → HTTP ALB → ECS. That path is not deployed in 16A. See [ADR-026](../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md) and [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md).

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

Phase 8D executed Deploy after live `OIDC_ISSUER`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL` were configured. Run `dd55327` used `target=both`. GitHub OIDC token exchange succeeded on Azure and AWS. The workflow built once and tagged `dd55327` and `stable`. ACR and ECR received the same digest `sha256:0590bf6f7b2ae5614dd35af0307763cb0303e98948531bab2352258e6773ed70`. Azure currently runs `eci-api:dd55327`. AWS currently uses task definition `eci-api-dev:4`. CD remains `workflow_dispatch` only.

Phase 9C verified PostgreSQL on GitHub Actions run `32336909759` (Lint and test success; PostgreSQL integration success; 34 tests; Alembic round-trip to revision `9a0001`). That job does not deploy and does not use a managed cloud database. Phase 9D does not run `deploy.yml`. Current Azure and AWS runtimes still do not have Phase 9 `DATABASE_URL`. Do not deploy the Phase 9 image until a colocated PostgreSQL database exists.

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

Azure: ACR admin disabled; managed-identity pull and Foundry authentication; operator `/32` HTTPS ingress with `allowInsecure=false`.

AWS: dedicated ECI security group; operator `/32` on TCP 8000; no `0.0.0.0/0` inbound on 8000; separate execution and task roles; least-privilege Bedrock `InvokeModel`; no NAT; no standing ALB after Phase 8B teardown.

Application-user JWT authentication is live at the API boundary (`AUTH_MODE=oidc`). Azure accepted a real bearer token over HTTPS. Never send a real bearer token over AWS HTTP.

## Ingress

Azure live: Container Apps HTTPS → ECI.

AWS current: operator `/32` HTTP to the Fargate task (verification-only).

AWS verified, not retained: HTTPS domain + ACM → ALB → ECS. Recreating that path requires a custom domain and ACM certificate.

## Phase 8D verification

| Capability | Azure | AWS |
|---|---|---|
| Application image deployment | verified | verified |
| GitHub OIDC deployment | verified | verified |
| Workload identity | verified | verified |
| Public health | verified HTTPS | verified controlled HTTP |
| Missing-token auth | verified | verified |
| JWKS/OIDC runtime | verified | verified (fake unknown-kid 401; no real bearer) |
| Real bearer authorized request | verified | deferred until AWS TLS |
| AI inference after auth | Foundry verified once | deferred until AWS TLS |
| Production TLS | ACA managed TLS | domain/ACM deferred |

## Cost controls

Azure: ACR Basic; Container Apps Consumption; min replicas 0; max replicas 1; Log Analytics 30-day retention; no Application Insights; no custom metrics; no dashboards/alerts. ACR Basic and Log Analytics ingestion/retention can incur charges.

AWS: one temporary 0.5 vCPU / 1 GiB Fargate task during verification; service returned to `desiredCount=0`, so Fargate compute is not running; no NAT Gateway; no ALB/NLB; CloudWatch Logs retention 1 day; Container Insights disabled. Retained ECR image storage and CloudWatch Logs storage/usage may incur charges.

This is not a zero-cost deployment.

## Observability

Phase 7 is implemented. The same image writes structured JSON to stdout on both clouds.

Azure: Container Apps environment `eci-ca-env-dev` sends logs to Log Analytics workspace `eci-law-dev` (30 days). Native Container Apps metrics (`Requests`, `ResponseTime`, `Replicas`, `CpuPercentage`, `MemoryPercentage`, `RestartCount`) were verified. Use Log Analytics for historical inspection. `az containerapp logs show` can wake a scale-to-zero replica and is for active diagnostics only.

AWS: current task definition is `eci-api-dev:4` (`dd55327`). CloudWatch log group `/ecs/eci-api-dev` retains logs for 1 day via awslogs. Standard AWS/ECS `CPUUtilization` and `MemoryUtilization` were verified. Container Insights remains disabled. The service stays at `desiredCount=0` when idle.

Phase 7 does not include distributed tracing, custom metrics, alerts, dashboards, or a full production SRE/SLO stack.

See [Observability](observability.md).

## CI/CD

See [GitHub Actions](#github-actions).

## Not implemented

- Azure App Service / AWS App Runner (not used; hosting is Container Apps and ECS Fargate)
- Azure Monitor / Amazon CloudWatch tracing, dashboards, and custom metrics (native log retention and platform metrics are in Phase 7)
- AWS persistent HTTPS / custom domain (domain and ACM deferred)
- automatic (push/tag) cloud deployment
- Phase 8B temporary IAM policy cleanup (`ECIPhase8BIngressVerificationPolicy`), if still attached — IAM-admin follow-up
- Azure Database for PostgreSQL / Amazon RDS (not provisioned; see [PostgreSQL persistence](persistence.md))
- Key Vault / Secrets Manager injection of `DATABASE_URL`
- Entra or RDS IAM database authentication
- automatic schema migration from application startup or from every replica

See [Cloud Roadmap](roadmap.md), [Authentication](authentication.md), and [Provider comparison](comparison.md).
