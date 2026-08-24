# AWS ECS Fargate — Phase 6C Runbook

Operator runbook for deploying the already verified ECI Docker image to Amazon ECS on Fargate in `eu-south-2`.

**Status:** Prompt 7 live deployment completed. Phase 7C pushed `phase7a-5f4f5f8`, registered task definition `eci-api-dev:2`, verified CloudWatch Logs and standard ECS metrics, then returned the service to `desiredCount=0`. ECR, cluster, service, both task-definition revisions, IAM roles, security group, and log group are retained. Do not re-run mutating commands unless a later prompt requests it. Do not delete these resources in documentation-only work.

## Current architecture vs this historical runbook (Phase 13)

This file remains the Phase 6C/7 AWS hosting procedure. Commands and resource names below are historical. They were not re-executed in Phase 13.

Current ECI application architecture (code and documentation; not a claim that the retained ECS service was redeployed):

- Application-user OIDC exists (`AUTH_MODE=oidc`; live Entra is the first IdP).
- Mailbox delegated OAuth is a separate identity domain from that login and from Bedrock.
- AWS Secrets Manager is the durable mailbox OAuth credential backend (`CREDENTIAL_STORE_BACKEND=aws_secrets_manager`). Runtime production identity is the ECS task role through the boto3 default credential chain. Settings hold region and namespace only. No AWS access keys in Settings.
- Least-privilege mailbox secret actions on `eci/mailbox-oauth/*`: `CreateSecret`, `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, `DescribeSecret`, `DeleteSecret`. `ListSecrets` is not required.
- Durable stores require PostgreSQL advisory-lock coordination. PostgreSQL does not store OAuth tokens.
- Phase 13E live-validated Secrets Manager at the store/factory path using the existing ECI developer identity. That is store validation, not a claim that `eci-api-dev` now runs Phase 13 mailbox OAuth.
- The operator IAM user (`eci-developer` / profile `eci-dev`) is **not** the production ECS application identity. The application uses `eci-bedrock-task-role-dev` (and would use that same task-role pattern for Secrets Manager in a production mailbox-OAuth deployment).
- The retained ECS service may still be the historical Phase 6C/7/8 image and has **not** been certified as a complete Phase 13 mailbox-OAuth runtime.

See [Authentication](../../docs/cloud/authentication.md), [Phase 13](../../docs/roadmap/phase-13-mailbox-delegated-oauth.md), and [ADR-023](../../docs/decisions/ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md).

## Current operational state (Phase 7)

```text
Region:                  eu-south-2
ECR repository:          eci-api-dev
Current image tag:       phase7a-5f4f5f8
Previous image tag:      phase6c (retained)
ECS cluster:             eci-cluster-dev
ECS service:             eci-api-dev
Current task definition: eci-api-dev:2
Previous revision:       eci-api-dev:1 (retained)
desiredCount:            0
runningCount:            0
Log group:               /ecs/eci-api-dev
Log retention:           1 day
Container Insights:      disabled
```

Historical inspection: CloudWatch Logs group `/ecs/eci-api-dev`. Quote `request_id` in filter patterns (hyphens are operators). Standard service metrics: namespace `AWS/ECS`, dimensions `ClusterName=eci-cluster-dev` and `ServiceName=eci-api-dev`, metrics `CPUUtilization` and `MemoryUtilization`.

Operator `eci-developer` (profile `eci-dev`) may call `cloudwatch:ListMetrics` and `cloudwatch:GetMetricStatistics`. Those permissions are not on `eci-bedrock-task-role-dev` or `eci-ecs-execution-role-dev`. Phase 7C did not call Bedrock and did not enable Container Insights.

## Purpose

Deploy the same Prompt 3 image:

```text
enterprise-communication-intelligence-eci:latest
→ Amazon ECR
→ Amazon ECS Fargate
→ ECS Task Role
→ boto3 / ECS container credential provider
→ Amazon Bedrock Runtime Converse
→ EU Claude Haiku 4.5 inference profile
```

Runtime configuration:

```text
AI_PROVIDER=amazon_bedrock
APP_ENV=production
BEDROCK_REGION=eu-south-2
BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

Never set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, or `AWS_PROFILE` on the task.

This is **not** the final production ingress architecture. Phase 6C proves the identity path with one Fargate task, a public ENI, and a security-group `/32` allow rule. There is no ALB, NAT Gateway, or custom VPC.

## Prompt 6 inspection result (read-only)

Verified:

- AWS CLI v2 and profile `eci-dev` authenticate (`sts get-caller-identity` succeeds).
- `eu-south-2` is reachable via Bedrock control plane.
- Inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0` is **ACTIVE**, type `SYSTEM_DEFINED`, name `EU Anthropic Claude Haiku 4.5`.
- Destination foundation-model regions: `eu-north-1`, `eu-west-3`, `eu-south-1`, `eu-south-2`, `eu-west-1`, `eu-central-1`.
- Local image `enterprise-communication-intelligence-eci:latest` is `linux/amd64` (Prompt 3 digest).

**Prompt 6 blocker (resolved before Prompt 7):** the `eci-dev` identity initially lacked ECR/ECS/IAM/EC2/Logs APIs. An administrator attached `ECIPhase6CDeploymentPolicy` to IAM user `eci-developer`. Prompt 7 preflight then succeeded.

Do not start mutating steps if those APIs are denied again.

## Identity model (keep two roles)

| Role | Name | Used by | Purpose |
|---|---|---|---|
| Task execution role | `eci-ecs-execution-role-dev` | ECS/Fargate platform | Pull from ECR; write `awslogs` |
| Task role | `eci-bedrock-task-role-dev` | ECI process | Bedrock `InvokeModel` via boto3 |

Do **not** merge these roles.

Fargate credentials:

```text
boto3 standard credential chain
→ ECS container credential provider
→ ECS Task Role
```

Do **not** describe this as EC2 instance metadata or instance-profile credentials.

## Proposed names

```text
Region:                  eu-south-2
ECR repository:          eci-api-dev
Image tag:               phase7a-5f4f5f8 (Phase 6C used phase6c; that tag remains)
ECS cluster:             eci-cluster-dev
Task definition family:  eci-api-dev
ECS service:             eci-api-dev
Container name:          eci-api
Execution role:          eci-ecs-execution-role-dev
Task role:               eci-bedrock-task-role-dev
Task-role policy:        eci-bedrock-invoke-dev
Security group:          eci-fargate-sg-dev
Log group:               /ecs/eci-api-dev
```

Tags on ECI-created resources only:

```text
Project=ECI
Environment=dev
Phase=6C
ManagedBy=manual
```

Do not tag the default VPC, default subnets, or internet gateway.

## ECR

- Private repository `eci-api-dev` in `eu-south-2`
- Inspect that named repository only; do not list all repositories in the account
- Scan on push: enabled
- Encryption: AES256 (ECR default; no CMK)
- Tag mutability: **MUTABLE** so Prompt 7 retries can overwrite `phase6c` without extra tags
- Push the Prompt 3 image; do not rebuild; do not use CodeBuild

## Networking

Default VPC reused for Fargate networking; not modified.

Preferred:

```text
existing default VPC
→ two public subnets in different AZs
→ Fargate awsvpc
→ assignPublicIp=ENABLED
```

No NAT Gateway, ALB/NLB, VPC endpoints, Route 53, or custom VPC for Phase 6C.

If Prompt 7 cannot find a default VPC with at least two public subnets and an internet-gateway default route, **stop**. Do not create a VPC unless a later prompt explicitly authorizes it.

Ingress security group `eci-fargate-sg-dev`:

- Inbound: TCP `8000` from operator public IPv4 `/32` only
- No `0.0.0.0/0` on 8000
- Outbound: leave the default new-SG egress (`0.0.0.0/0`) so the task can reach ECR, Bedrock HTTPS, and CloudWatch Logs

Do not write the operator IP into this repository.

## Logging and metrics

Log group `/ecs/eci-api-dev`, retention **1 day**, driver `awslogs`. Phase 7C verified structured Phase 7A JSON in this group. Standard AWS/ECS `CPUUtilization` and `MemoryUtilization` are the service metrics in use. No Container Insights, alarms, X-Ray, custom metrics, or Application Insights.

`ECIPhase6CDeploymentPolicy` (or an equivalent operator grant) now includes `cloudwatch:ListMetrics` and `cloudwatch:GetMetricStatistics` for inspection. Do not add CloudWatch write permissions to the application.

## Cost control

During verification: one Fargate task, 0.5 vCPU / 1 GiB (`cpu=512`, `memory=1024`).

After verification: `desiredCount=0` (no running task, no live IP). Retain ECR, cluster, task definition, service definition, IAM roles, security group, and log group for later phases.

Fargate compute is not running at `desiredCount=0`. ECS orchestration and IAM roles/policies have no usage charge. Retained ECR image storage and CloudWatch Logs storage/usage may incur charges.

## Cleanup (do not run in Prompt 7 success path)

When cleanup is later requested, in this order:

1. `desiredCount=0` (if not already)
2. Delete ECS service
3. Deregister ECI task-definition revisions (`eci-api-dev`)
4. Delete ECS cluster `eci-cluster-dev`
5. Delete ECR repository `eci-api-dev` (including images)
6. Delete security group `eci-fargate-sg-dev`
7. Delete log group `/ecs/eci-api-dev`
8. Detach `AmazonECSTaskExecutionRolePolicy` and delete `eci-ecs-execution-role-dev`
9. Delete inline policy `eci-bedrock-invoke-dev` and role `eci-bedrock-task-role-dev`

Never delete the default VPC, default subnets, route tables, internet gateway, default security group, `AWSServiceRoleForECS`, or Bedrock inference profiles.

---

## Operator IAM prerequisite

Prompt 6 initially found that IAM user `eci-developer` (CLI profile `eci-dev`) lacked ECR/ECS/IAM/EC2/Logs APIs. An administrator attached customer-managed policy `ECIPhase6CDeploymentPolicy` to `eci-developer`. Prompt 7 preflight then succeeded.

`ECIPhase6CDeploymentPolicy` is a customer-managed least-privilege deployment policy for the Phase 6C ECR/ECS/IAM/EC2/CloudWatch operator workflow. It does not grant the application Bedrock credentials. Bedrock `InvokeModel` belongs on `eci-bedrock-task-role-dev`.

This repository does not store the policy JSON or account IDs.

IAM roles were created without tags because `iam:TagRole` was intentionally not granted.

Do not attach `AdministratorAccess` or `AmazonBedrockFullAccess` to the task role.

The operator workflow requires at least:

```text
sts:GetCallerIdentity
ecr:CreateRepository, ecr:DescribeRepositories, ecr:GetAuthorizationToken,
  ecr:BatchCheckLayerAvailability, ecr:InitiateLayerUpload, ecr:UploadLayerPart,
  ecr:CompleteLayerUpload, ecr:PutImage, ecr:BatchGetImage
ecs:CreateCluster, ecs:DescribeClusters, ecs:ListClusters,
  ecs:RegisterTaskDefinition, ecs:DescribeTaskDefinition, ecs:ListTaskDefinitions,
  ecs:DeregisterTaskDefinition,
  ecs:CreateService, ecs:UpdateService, ecs:DescribeServices, ecs:ListServices,
  ecs:DescribeTasks, ecs:ListTasks
iam:CreateRole, iam:GetRole, iam:AttachRolePolicy, iam:PutRolePolicy,
  iam:PassRole (on the two ECI roles, to ecs-tasks.amazonaws.com),
  iam:CreateServiceLinkedRole (for ECS if AWSServiceRoleForECS is missing)
ec2:DescribeVpcs, ec2:DescribeSubnets, ec2:DescribeRouteTables,
  ec2:DescribeInternetGateways, ec2:DescribeSecurityGroups,
  ec2:DescribeNetworkInterfaces, ec2:DescribeAvailabilityZones,
  ec2:CreateSecurityGroup, ec2:AuthorizeSecurityGroupIngress,
  ec2:CreateTags
logs:CreateLogGroup, logs:DescribeLogGroups, logs:PutRetentionPolicy, logs:GetLogEvents
cloudwatch:ListMetrics, cloudwatch:GetMetricStatistics
```

Bedrock `InvokeModel` is **not** required on the operator.

---

## Prompt 7 execution

Run from Bash in WSL at the repository root. Commands stop on failure.

Use profile `eci-dev` only for operator CLI. Do not export `AWS_PROFILE` into the task.

### 1. Confirm profile, region, and local image

```bash
set -euo pipefail

AWS_PROFILE_NAME="eci-dev"
AWS_REGION="eu-south-2"
LOCAL_IMAGE="enterprise-communication-intelligence-eci:latest"

aws sts get-caller-identity --profile "${AWS_PROFILE_NAME}" >/dev/null
docker image inspect "${LOCAL_IMAGE}" >/dev/null
```

If authentication expired:

```bash
aws login --profile eci-dev
```

Do not switch profiles silently.

### 2. Define names

```bash
ECR_REPO="eci-api-dev"
IMAGE_TAG="phase6c"
ECS_CLUSTER="eci-cluster-dev"
ECS_SERVICE="eci-api-dev"
TASK_FAMILY="eci-api-dev"
CONTAINER_NAME="eci-api"
TASK_EXEC_ROLE="eci-ecs-execution-role-dev"
TASK_ROLE="eci-bedrock-task-role-dev"
TASK_ROLE_POLICY="eci-bedrock-invoke-dev"
SECURITY_GROUP_NAME="eci-fargate-sg-dev"
LOG_GROUP="/ecs/eci-api-dev"
BEDROCK_MODEL_ID="eu.anthropic.claude-haiku-4-5-20251001-v1:0"

ACCOUNT_ID="$(aws sts get-caller-identity --profile "${AWS_PROFILE_NAME}" --query Account --output text)"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
REMOTE_IMAGE="${ECR_REGISTRY}/${ECR_REPO}:${IMAGE_TAG}"
INFERENCE_PROFILE_ARN="arn:aws:bedrock:${AWS_REGION}:${ACCOUNT_ID}:inference-profile/${BEDROCK_MODEL_ID}"
```

Do not print `${ACCOUNT_ID}` into git-tracked files.

### 3. Preflight — stop if still AccessDenied

```bash
# Inspect eci-api-dev only. Do not list all repositories.
# RepositoryNotFoundException is acceptable before create. AccessDenied must stop.
aws ecr describe-repositories \
  --repository-names "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"
aws ecs list-clusters --region "${AWS_REGION}" --profile "${AWS_PROFILE_NAME}" >/dev/null
aws iam get-role --role-name AWSServiceRoleForECS --profile "${AWS_PROFILE_NAME}" >/dev/null \
  || echo "AWSServiceRoleForECS not visible yet; ECS may create it on first cluster create."
aws ec2 describe-vpcs --filters Name=is-default,Values=true --region "${AWS_REGION}" --profile "${AWS_PROFILE_NAME}" >/dev/null
aws logs describe-log-groups --log-group-name-prefix "${LOG_GROUP}" --region "${AWS_REGION}" --profile "${AWS_PROFILE_NAME}" >/dev/null
```

If any required describe/list call is AccessDenied, **stop**. Do not create partial resources. A missing named ECR repository is acceptable before the create step.

### 4. Re-check name collisions

If any proposed name already exists and is not an ECI Phase 6C resource, **stop** and choose a smaller suffix. Do not overwrite unrelated resources.

### 5. Select two public subnets

```bash
VPC_ID="$(aws ec2 describe-vpcs \
  --filters Name=is-default,Values=true \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --query 'Vpcs[0].VpcId' \
  --output text)"

# Prefer default-for-AZ public subnets in different AZs.
mapfile -t SUBNET_IDS < <(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=default-for-az,Values=true" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --query 'Subnets[?MapPublicIpOnLaunch==`true`].SubnetId' \
  --output text | tr '\t' '\n' | head -n 2)

if [ "${#SUBNET_IDS[@]}" -lt 2 ]; then
  echo "Need two public subnets in the default VPC. Stop."
  exit 1
fi

SUBNET_A="${SUBNET_IDS[0]}"
SUBNET_B="${SUBNET_IDS[1]}"
```

Confirm each selected subnet's route table has a default route (`0.0.0.0/0`) to an internet gateway. If not, **stop**.

### 6. Discover operator public IPv4

```bash
OPERATOR_IP="$(curl -4 -fsS https://api.ipify.org)"
if ! printf '%s' "${OPERATOR_IP}" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "Failed to obtain operator IPv4. Stop before creating ingress."
  exit 1
fi
OPERATOR_CIDR="${OPERATOR_IP}/32"
```

Do not commit this value.

### 7. Create ECR repository

```bash
aws ecr create-repository \
  --repository-name "${ECR_REPO}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --image-tag-mutability MUTABLE \
  --image-scanning-configuration scanOnPush=true \
  --encryption-configuration encryptionType=AES256 \
  --tags Key=Project,Value=ECI Key=Environment,Value=dev Key=Phase,Value=6C Key=ManagedBy,Value=manual
```

### 8. Login, tag, and push the verified image

On this WSL host the default Docker credential helper failed (`The stub received bad data`). Use an isolated Docker config for the operator login only:

```bash
DOCKER_CONFIG="$(mktemp -d /tmp/eci-docker-config-XXXX)"
export DOCKER_CONFIG
printf '%s\n' '{}' > "${DOCKER_CONFIG}/config.json"

aws ecr get-login-password --region "${AWS_REGION}" --profile "${AWS_PROFILE_NAME}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

docker tag "${LOCAL_IMAGE}" "${REMOTE_IMAGE}"

LOCAL_ID="$(docker image inspect "${LOCAL_IMAGE}" --format '{{.Id}}')"
REMOTE_ID="$(docker image inspect "${REMOTE_IMAGE}" --format '{{.Id}}')"
if [ "${LOCAL_ID}" != "${REMOTE_ID}" ]; then
  echo "Tagged image does not match Prompt 3 image. Stop."
  exit 1
fi

docker push "${REMOTE_IMAGE}"
rm -rf "${DOCKER_CONFIG}"
unset DOCKER_CONFIG
```

Operator Docker login is a CLI session only. Never put the password in the image, task definition, or git.

### 9. Create the ECS task execution role

```bash
aws iam create-role \
  --role-name "${TASK_EXEC_ROLE}" \
  --profile "${AWS_PROFILE_NAME}" \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

aws iam attach-role-policy \
  --role-name "${TASK_EXEC_ROLE}" \
  --profile "${AWS_PROFILE_NAME}" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

Do not attach Bedrock permissions to this role. Do not tag IAM roles (`iam:TagRole` is not granted to the deployment user).

### 10. Create the application task role and least-privilege Bedrock policy

`bedrock:InvokeModel` only. Scope:

1. The EU inference-profile ARN in `eu-south-2` (account discovered at runtime).
2. The six Claude Haiku 4.5 foundation-model ARNs from the live inference-profile `models` list.
3. Foundation-model invoke allowed only when `bedrock:InferenceProfileArn` matches that profile.

```bash
aws iam create-role \
  --role-name "${TASK_ROLE}" \
  --profile "${AWS_PROFILE_NAME}" \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

POLICY_FILE="$(mktemp /tmp/eci-bedrock-invoke-XXXX.json)"
cat > "${POLICY_FILE}" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeEuHaikuInferenceProfile",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": "${INFERENCE_PROFILE_ARN}"
    },
    {
      "Sid": "InvokeHaikuFoundationModelsViaProfile",
      "Effect": "Allow",
      "Action": "bedrock:InvokeModel",
      "Resource": [
        "arn:aws:bedrock:eu-north-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-west-3::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-south-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-south-2::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0",
        "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-haiku-4-5-20251001-v1:0"
      ],
      "Condition": {
        "StringEquals": {
          "bedrock:InferenceProfileArn": "${INFERENCE_PROFILE_ARN}"
        }
      }
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name "${TASK_ROLE}" \
  --policy-name "${TASK_ROLE_POLICY}" \
  --policy-document "file://${POLICY_FILE}" \
  --profile "${AWS_PROFILE_NAME}"

rm -f "${POLICY_FILE}"
```

Do not grant `bedrock:*` or `AmazonBedrockFullAccess`.

### 11. Create the log group

```bash
aws logs create-log-group \
  --log-group-name "${LOG_GROUP}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --tags Project=ECI,Environment=dev,Phase=6C,ManagedBy=manual

aws logs put-retention-policy \
  --log-group-name "${LOG_GROUP}" \
  --retention-in-days 1 \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"
```

### 12. Create the security group and operator /32 rule

```bash
SG_ID="$(aws ec2 create-security-group \
  --group-name "${SECURITY_GROUP_NAME}" \
  --description "ECI Phase 6C Fargate operator-only ingress" \
  --vpc-id "${VPC_ID}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --tag-specifications 'ResourceType=security-group,Tags=[{Key=Project,Value=ECI},{Key=Environment,Value=dev},{Key=Phase,Value=6C},{Key=ManagedBy,Value=manual}]' \
  --query GroupId \
  --output text)"

aws ec2 authorize-security-group-ingress \
  --group-id "${SG_ID}" \
  --protocol tcp \
  --port 8000 \
  --cidr "${OPERATOR_CIDR}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"
```

Default egress (`0.0.0.0/0`) remains. Do not add `0.0.0.0/0` inbound on 8000.

### 13. Create the ECS cluster

```bash
aws ecs create-cluster \
  --cluster-name "${ECS_CLUSTER}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --tags key=Project,value=ECI key=Environment,value=dev key=Phase,value=6C key=ManagedBy,value=manual
```

Do not enable Container Insights, Service Connect, or ECS Exec.

If cluster create fails because `AWSServiceRoleForECS` is missing, the operator needs `iam:CreateServiceLinkedRole` for ECS. Do not create unrelated service-linked roles.

### 14. Register the Fargate task definition

Generate JSON in `/tmp` (do not commit it).

```bash
EXEC_ROLE_ARN="$(aws iam get-role --role-name "${TASK_EXEC_ROLE}" --profile "${AWS_PROFILE_NAME}" --query Role.Arn --output text)"
TASK_ROLE_ARN="$(aws iam get-role --role-name "${TASK_ROLE}" --profile "${AWS_PROFILE_NAME}" --query Role.Arn --output text)"

TASK_DEF_FILE="$(mktemp /tmp/eci-taskdef-XXXX.json)"
cat > "${TASK_DEF_FILE}" <<EOF
{
  "family": "${TASK_FAMILY}",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "${EXEC_ROLE_ARN}",
  "taskRoleArn": "${TASK_ROLE_ARN}",
  "runtimePlatform": {
    "cpuArchitecture": "X86_64",
    "operatingSystemFamily": "LINUX"
  },
  "containerDefinitions": [
    {
      "name": "${CONTAINER_NAME}",
      "image": "${REMOTE_IMAGE}",
      "essential": true,
      "portMappings": [
        {"containerPort": 8000, "protocol": "tcp"}
      ],
      "environment": [
        {"name": "AI_PROVIDER", "value": "amazon_bedrock"},
        {"name": "APP_ENV", "value": "production"},
        {"name": "BEDROCK_REGION", "value": "${AWS_REGION}"},
        {"name": "BEDROCK_MODEL_ID", "value": "${BEDROCK_MODEL_ID}"}
      ],
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)\" || exit 1"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 20
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "${LOG_GROUP}",
          "awslogs-region": "${AWS_REGION}",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF

aws ecs register-task-definition \
  --cli-input-json "file://${TASK_DEF_FILE}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"

rm -f "${TASK_DEF_FILE}"
```

Confirm the registered container environment does **not** include AWS access keys, session token, or `AWS_PROFILE`.

### 15. Create the service (desired count 1)

```bash
aws ecs create-service \
  --cluster "${ECS_CLUSTER}" \
  --service-name "${ECS_SERVICE}" \
  --task-definition "${TASK_FAMILY}" \
  --desired-count 1 \
  --launch-type FARGATE \
  --platform-version LATEST \
  --deployment-configuration "deploymentCircuitBreaker={enable=true,rollback=true}" \
  --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_A},${SUBNET_B}],securityGroups=[${SG_ID}],assignPublicIp=ENABLED}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --tags key=Project,value=ECI key=Environment,value=dev key=Phase,value=6C key=ManagedBy,value=manual
```

No load balancer. No service discovery. No autoscaling.

Wait until the service has a running task:

```bash
aws ecs wait services-stable \
  --cluster "${ECS_CLUSTER}" \
  --services "${ECS_SERVICE}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"
```

### 16. Discover the task public IPv4

```bash
TASK_ARN="$(aws ecs list-tasks \
  --cluster "${ECS_CLUSTER}" \
  --service-name "${ECS_SERVICE}" \
  --desired-status RUNNING \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --query 'taskArns[0]' \
  --output text)"

ENI_ID="$(aws ecs describe-tasks \
  --cluster "${ECS_CLUSTER}" \
  --tasks "${TASK_ARN}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text)"

TASK_PUBLIC_IP="$(aws ec2 describe-network-interfaces \
  --network-interface-ids "${ENI_ID}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}" \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text)"

if [ -z "${TASK_PUBLIC_IP}" ] || [ "${TASK_PUBLIC_IP}" = "None" ]; then
  echo "No public IPv4 on the task ENI. Stop."
  exit 1
fi
```

The IP can change if the task is replaced. Do not hard-code it.

### 17. Health, readiness, and production env

```bash
BASE="http://${TASK_PUBLIC_IP}:8000"

curl --fail --silent --show-error --max-time 120 "${BASE}/health"
curl --fail --silent --show-error --max-time 120 "${BASE}/api/v1/readiness"
curl --fail --silent --show-error --max-time 120 "${BASE}/api/v1/health"
```

Expect HTTP 200, readiness `ready`, and `environment=production`.

### 18. Live ECI → Bedrock analysis (one request)

This is paid Bedrock inference. Run once.

```bash
curl --fail --silent --show-error --max-time 180 \
  -X POST "${BASE}/api/v1/communications/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "Please review the Phase 6C AWS deployment report and confirm receipt.",
      "message_id": "aws-fargate-live-001",
      "metadata": {
        "source_type": "email",
        "sender": "manager@example.com",
        "recipients": ["user@example.com"],
        "subject": "Phase 6C AWS deployment report"
      }
    },
    "include_draft_reply": true,
    "include_action_items": true
  }'
```

Expect HTTP 200 and `"provider": "amazon_bedrock"`.

That result is the identity proof:

```text
no AWS_PROFILE in the task
+ no static keys
+ boto3 used the ECS container credential provider
+ eci-bedrock-task-role-dev authorized InvokeModel
```

Do not print ECS credential contents. Do not query `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` values.

If 401/403: check task role attachment, inline policy ARNs, inference-profile condition, and IAM propagation. Do not add access keys.

### 19. Inspect deployment logs if needed

```bash
aws logs tail "${LOG_GROUP}" \
  --since 30m \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"
```

Look for `application_startup`, `communication_analysis_request_received`, `communication_analysis_completed`. No observability products.

### 20. Scale to zero after verification

```bash
aws ecs update-service \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --desired-count 0 \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"

aws ecs wait services-stable \
  --cluster "${ECS_CLUSTER}" \
  --services "${ECS_SERVICE}" \
  --region "${AWS_REGION}" \
  --profile "${AWS_PROFILE_NAME}"
```

Confirm running task count is 0. The public task IP will no longer exist. Leave ECR, cluster, task definition, service, IAM, SG, and log group in place. Do not delete resources on success.

---

## Out of scope

Historical Phase 6C scope for this runbook (not a current-architecture claim):

- Terraform / CloudFormation / CDK / GitHub Actions
- ALB, NAT, private subnets, VPC endpoints
- Application-user authentication (added later in Phase 8; see the Phase 13 addendum above)
- Azure changes
- Rebuilding the Docker image
- Changing ECI application code
