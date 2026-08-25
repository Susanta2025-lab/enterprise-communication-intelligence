# ADR-026: Cloud-hosted browser SPA topology and multi-cloud HTTPS validation

## Status

Accepted

The decision is frozen in Phase 16A from authenticated read-only inventory plus current application contracts. No cloud resources were created or mutated in 16A. Implementation is Phase 16B–16F.

## Date

Phase 16 (Cloud-Hosted Browser & End-to-End Multi-Cloud Validation)

## Context

Phase 15 certified the browser SPA against local Vite, local FastAPI, and local PostgreSQL. Retained Azure Container Apps and Amazon ECS runtimes still serve the Phase 8 image (`eci-api:dd55327` / `eci-api-dev:4`), operator `/32` ingress, and no colocated PostgreSQL. ADR-010 recorded Azure Container Apps managed HTTPS as live ingress and AWS ALB HTTPS as verified then torn down, with custom domain plus ACM required before ALB-native TLS could return.

Phase 16 must prove:

```text
HTTPS SPA
→ Entra/MSAL
→ cloud FastAPI
→ durable PostgreSQL
→ durable mailbox credential store
→ real mailbox read
→ real Foundry / Bedrock
→ Analyze
→ Propose
→ Approve
→ STOP before Send
```

Bearer tokens, OAuth callbacks, and browser origins require public HTTPS. Direct ECS task HTTP remains unsafe for real tokens. CloudFront cannot target an ephemeral Fargate public IP: the IP changes, `desiredCount=0` removes the origin, and there is no stable task hostname.

## Decision

Deploy **environment-specific frontends** from the same `frontend/` source. Do not add an in-app backend or cloud selector. Use **per-environment Vite builds** (`VITE_*` at build time). Do not introduce runtime config JSON unless a later slice proves it necessary.

### Azure

```text
Azure Static Web Apps (managed HTTPS)
→ Azure Container Apps `eci-api-dev` (managed HTTPS)
→ Azure Database for PostgreSQL Flexible Server (colocated)
→ Azure Key Vault `eci-kv-oauth-dev-susanta`
→ Microsoft Foundry
```

Reuse existing ACA, ACR, UAMI, Log Analytics, Foundry, and Key Vault. Create Static Web Apps and PostgreSQL later under explicit authorization. Do not delete `rg-eci-dev`.

### AWS

```text
S3 (private) + CloudFront Origin Access Control
→ default `*.cloudfront.net` HTTPS SPA hostname

CloudFront (default `*.cloudfront.net` HTTPS, API caching disabled)
→ Application Load Balancer HTTP:80
→ ECS Fargate `eci-api-dev` :8000
→ Amazon RDS PostgreSQL (colocated)
→ AWS Secrets Manager namespace `eci/mailbox-oauth`
→ Amazon Bedrock
```

CloudFront is the browser and OAuth HTTPS identity. The ALB is the stable ECS origin. HTTP exists only on the CloudFront→ALB origin hop. Restrict the ALB security group to the CloudFront managed prefix list so browsers do not call the ALB as a public HTTP origin. Change `eci-fargate-sg-dev` so port 8000 accepts the ALB security group, not operator `/32` as the sole browser path.

**Custom domain is not required.** ALB-native HTTPS still needs ACM and a domain you control (ADR-010). CloudFront default certificates remove that blocker for Phase 16.

Reuse existing ECR, ECS cluster/service, execution role, task role, log group, and Bedrock inference profile. Create S3, CloudFront, ALB/target group/listener, and RDS later under explicit authorization. After the AWS proof, ALB may be deleted again for cost control (same pattern as Phase 8B). ECS may return to `desiredCount=0`. ALB hourly cost is unavoidable while that API path exists.

### Identity reuse

Reuse Entra SPA `eci-web-dev` and resource API `eci-api-auth-dev`. Do not create `eci-web-azure` / `eci-web-aws` or duplicate ECI scopes. Keep the localhost SPA redirect. Add cloud HTTPS SPA redirects later under explicit Entra authorization. Reuse existing Gmail and Microsoft mailbox OAuth apps by adding cloud HTTPS callback URIs; keep local callbacks.

### Data and credentials

Use **colocated PostgreSQL per cloud proof**, not one shared cross-cloud database. Provision Azure PostgreSQL and Amazon RDS **sequentially** so two paid databases are not left standing for symmetry. Run `alembic upgrade head` (current head `13a0001`) once per new database. Durable credential mutation continues to use PostgreSQL advisory locks. Cloud proofs must use:

- Azure: `CREDENTIAL_STORE_BACKEND=azure_key_vault`
- AWS: `CREDENTIAL_STORE_BACKEND=aws_secrets_manager`

Production cloud proofs must not use the in-memory credential store. Credentials must survive API process/task restart without forcing normal reauthorization.

### Live proof matrix

Crossed minimum only:

- Azure: Microsoft Graph mailbox → Microsoft Foundry
- AWS: Gmail mailbox → Amazon Bedrock

Do not require Gmail on Azure or Graph on AWS unless a provider-specific cloud defect appears. Live Send is not a Phase 16 exit criterion.

### Delivery

Do not introduce Terraform, Bicep, CDK, or CloudFormation in Phase 16. Continue controlled runbooks plus manual `workflow_dispatch` GitHub Actions. Do not enable automatic production deployment.

## Alternatives Considered

- **In-app backend/cloud selector or runtime config JSON** — rejected. Per-environment builds keep the SPA a public client with no extra attack surface.
- **Azure App Service or hosting the SPA on ACA** — rejected. Static Web Apps is SPA-native HTTPS with lower operational overhead and a clean split from the API.
- **Public S3 website hosting** — rejected. Prefer CloudFront Origin Access Control and a private bucket.
- **ALB HTTPS with ACM as the only AWS API path** — rejected for Phase 16 because it reimposes the ADR-010 custom-domain requirement.
- **CloudFront directly to ECS tasks** — rejected. No stable origin; public IPs churn; scale-to-zero removes the target.
- **API Gateway as the primary HTTPS layer** — rejected. It still needs NLB/ALB/VPC Link to reach Fargate and adds another product without removing standing load-balancer cost.
- **Shared cross-cloud PostgreSQL** — rejected (ADR-014). Latency, transfer cost, and coupled outages.
- **Dual standing managed databases for symmetry** — rejected. Sequential validation controls cost.
- **IaC platform in Phase 16** — rejected. Scope is deployment certification, not infrastructure-platform engineering.

## Consequences

- Azure browser proof reuses ACA managed HTTPS. 16B opened ingress beyond operator `/32` and replaced the Phase 8 image with current `master` (`eci-api:7518360`).
- Azure Static Web Apps control-plane location is West US 2. Spain Central is not a SWA region; West Europe refused new SWA customers. Static content is still served from the SWA global edge. Hostname: `https://witty-island-03f5de51e.7.azurestaticapps.net`.
- Runtime UAMI requires **Key Vault Secrets Officer** (not Secrets User) because the credential store calls get, set, and delete.
- AWS browser proof requires new CloudFront, S3, and ALB resources; ALB has standing cost during 16D/16E.
- Entra and mailbox OAuth apps gain extra HTTPS redirect/callback URIs; they are not replaced.
- Key Vault and Secrets Manager become mandatory cloud credential stores. Azure runtime UAMI has Key Vault Secrets Officer (16B). ECS task role still needs Secrets Manager data-plane permissions in 16D.
- ADR-010 remains the historical ALB-native TLS decision. This ADR selects CloudFront default HTTPS in front of HTTP ALB so Phase 16 does not wait on a custom domain.

## Benefits

- real HTTPS bearer-token paths on both clouds without custom domains
- portfolio-relevant split of SPA and API
- cost control through sequential databases, scale-to-zero compute, and optional ALB teardown
- same Entra SPA and resource API on both clouds

## Trade-offs

- AWS API path has an extra hop (CloudFront → ALB → ECS)
- ALB bills while retained, even if ECS is at `desiredCount=0`
- two frontend builds must stay in sync with backend origins
- ACA ingress must become reachable by browsers and OAuth providers; network `/32` is no longer the primary access control

## Related Components

- [ADR-010](ADR-010-multi-cloud-ingress.md) (historical AWS HTTPS / custom-domain gate)
- [ADR-014](ADR-014-cloud-postgresql-deployment-strategy.md)
- [ADR-022](ADR-022-opaque-communication-credential-store-and-refreshable-access-tokens.md)
- [ADR-025](ADR-025-browser-frontend-and-authentication-architecture.md)
- [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md)
- `frontend/src/config/env.ts`
- `app/core/config.py`
