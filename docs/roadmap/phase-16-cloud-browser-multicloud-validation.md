# Phase 16 — Cloud-Hosted Browser & End-to-End Multi-Cloud Validation

## Objective

Certify the existing ECI SPA and FastAPI against cloud HTTPS hosting, colocated PostgreSQL, durable mailbox credential stores, and real cloud AI — without live Send and without introducing an in-app cloud selector.

```text
HTTPS SPA
→ Entra/MSAL (`eci-web-dev`)
→ cloud FastAPI (`eci-api-auth-dev`)
→ colocated PostgreSQL
→ durable credential store
→ real mailbox read
→ real Foundry / Bedrock
→ Analyze → Propose → Approve
→ STOP before Send
```

Phase 16A establishes inventory, architecture freeze, configuration matrices, and authorization/cost gates. Later slices mutate cloud resources only after `BLOCKED — USER AUTHORIZATION REQUIRED`.

Baseline commit (Phase 15 closure): `b1267c440279c9804e27c2d2b747c6c7caf408a2`.

## Status

Phase 16A is **Completed**. Phases 16B–16F are **Not started**.

- **16A is Completed:** authenticated read-only Azure and AWS inventory; topology freeze; ADR-026; configuration/cost/authorization matrices; offline regression. No cloud mutation.
- **16B is Not started:** Azure full-stack browser deployment.
- **16C is Not started:** Azure live mailbox → Microsoft Foundry validation.
- **16D is Not started:** AWS HTTPS + full-stack browser deployment.
- **16E is Not started:** AWS live mailbox → Amazon Bedrock validation.
- **16F is Not started:** cross-cloud parity, security/cost hardening, final documentation.

Architecture: [ADR-026](../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md).

## Frozen topology

### Azure

```text
Azure Static Web Apps
→ Azure Container Apps `eci-api-dev`
→ Azure Database for PostgreSQL Flexible Server
→ Azure Key Vault
→ Microsoft Graph mailbox
→ MicrosoftFoundryProvider
```

Current ACA HTTPS FQDN (reuse): `eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io`

Future SPA origin: `https://<azure-swa-host>` (generated at SWA create; do not invent it).

### AWS

```text
S3 (private) + CloudFront OAC
→ default `*.cloudfront.net` SPA hostname

CloudFront (default HTTPS, API cache disabled)
→ ALB HTTP:80 (SG: CloudFront prefix list)
→ ECS Fargate `eci-api-dev` :8000
→ Amazon RDS PostgreSQL
→ AWS Secrets Manager
→ Gmail mailbox
→ AmazonBedrockProvider
```

Future SPA origin: `https://<aws-spa-cloudfront-host>`

Future API origin: `https://<aws-api-cloudfront-host>`

Custom domain: **not required**.

### Shared rules

- Same `frontend/` source; per-environment Vite builds; no runtime backend switcher.
- Reuse `eci-web-dev` and `eci-api-auth-dev`. Do not duplicate ECI scopes.
- Colocated PostgreSQL per cloud. Sequential provisioning. No shared cross-cloud database.
- Cloud credential stores are mandatory: Key Vault on Azure, Secrets Manager on AWS. Never `memory` for cloud proof.
- Live Send is not a Phase 16 exit criterion.
- No Terraform / Bicep / CDK / CloudFormation in Phase 16.
- CD remains manual `workflow_dispatch`.

## Cost-gate policy

Before any paid or billable create, stop with `BLOCKED — USER AUTHORIZATION REQUIRED` and report:

1. exact resource
2. provider/region
3. reason
4. whether an existing resource can be reused
5. cost category
6. scale-to-zero / stop capability
7. cleanup option
8. data-loss implications
9. exact proposed mutation

Do not bundle several expensive resources into one silent authorization.

---

## 16A — Cloud Runtime / Deployment Readiness

**Status: Completed.**

### Objective

Establish current cloud state, freeze Phase 16 topology, and produce implementation-ready configuration, cost, and authorization plans. No deployment.

### Planned cloud mutations

None.

### Authorization gates

Completed: Azure read-only inventory (`ECI-Development`); AWS read-only inventory (account `034456343525`, profile `eci-dev`, region `eu-south-2`).

### Cost gates

None consumed. Inventory was control-plane metadata only.

### Live validation boundary

No Gmail, Graph, Foundry, Bedrock, or Send.

### Expected tests

Offline Settings/CORS/OIDC/credential-store/AI-factory tests; frontend config/MSAL/API-base/scope tests; full frontend and backend regression.

### Exit criteria

Inventory, reuse/create matrices, HTTPS topology, environment matrices, ADR-026, this roadmap, and offline regression. Working tree left unstaged/uncommitted.

---

## 16B — Azure Full-Stack Browser Deployment

**Status: Not started.**

### Objective

Host the Azure SPA on Static Web Apps and run current `master` on ACA with PostgreSQL, Key Vault, CORS, and OAuth return — reachable by browser and OAuth callbacks over HTTPS.

### Planned cloud mutations (each a separate gate)

- ACR push of current image
- ACA image + environment update
- ACA ingress change (operator `/32` → public HTTPS; OIDC remains access control)
- Azure Static Web Apps create
- Azure Database for PostgreSQL Flexible Server create
- Key Vault RBAC for UAMI (`Key Vault Secrets User` or equivalent)
- Entra `eci-web-dev` HTTPS SPA redirect
- Gmail and Microsoft mailbox HTTPS callbacks on the ACA FQDN
- `alembic upgrade head` against the new Azure database

### Authorization gates

Separate `BLOCKED — USER AUTHORIZATION REQUIRED` for SWA create, PostgreSQL create, ACA image/config, ACA ingress, Key Vault RBAC, Entra redirect, and mailbox callback URI adds.

### Cost gates

PostgreSQL Flexible Server is **material** (stop/start may still bill storage). SWA is low/usage. ACA already exists (min replicas 0). Foundry is not invoked in 16B.

### Live validation boundary

Browser MSAL against ACA is in scope. Live mailbox OAuth and Foundry inference wait for 16C. No Send.

### Expected tests

Offline regression plus operator HTTPS smoke (health/OIDC) after deploy. No live mailbox/AI unless a later 16B prompt explicitly authorizes a narrow check.

### Exit criteria

Azure SPA origin live; ACA serving current image with production Settings names below; PostgreSQL migrated; Key Vault backend selected; CORS and `FRONTEND_OAUTH_RETURN_URL` set to the SWA origin; ingress allows browser and OAuth providers.

---

## 16C — Azure Live Mailbox → Microsoft Foundry Validation

**Status: Not started.**

### Objective

Prove Graph mailbox → Foundry analyze → propose → approve on Azure. Stop before Send.

### Planned cloud mutations

None required if 16B configuration is complete. Optional: one Foundry inference. No Send.

### Authorization gates

Live Microsoft mailbox OAuth; live Foundry inference. Each separate.

### Cost gates

Foundry: **one** selected-message real analysis unless an explicit retry is required after failure. Avoid repeated calls.

### Live validation boundary

Microsoft Graph mailbox on Azure only. Not Gmail. Not Send. Not Bedrock.

### Expected tests

Controlled live path plus offline regression if code changed (expected: configuration only).

### Exit criteria

Delegated Graph credentials persist across ACA replica recycle without normal reauthorization; one Foundry mailbox analysis; Propose → Approve; stop before Send.

---

## 16D — AWS HTTPS + Full-Stack Browser Deployment

**Status: Not started.**

### Objective

Create the frozen AWS HTTPS path and deploy current `master` with RDS, Secrets Manager, CORS, and OAuth return.

### Planned cloud mutations (each a separate gate)

- S3 frontend bucket (private)
- CloudFront SPA distribution (OAC, default HTTPS hostname)
- CloudFront API distribution (default HTTPS, cache disabled)
- ALB + target group + HTTP listener (standing cost)
- Security-group updates (ALB ← CloudFront prefix list; Fargate ← ALB)
- RDS PostgreSQL create
- ECS task definition / service update (image, env names, load balancer)
- Task-role Secrets Manager permissions on `eci/mailbox-oauth/*` (no `ListSecrets`)
- Entra SPA HTTPS redirect for the CloudFront SPA host
- Gmail HTTPS callback on the CloudFront API host
- `alembic upgrade head` against RDS

Prefer completing Azure 16B/16C first, then **stop Azure PostgreSQL** (or equivalent) before RDS create so two paid databases are not standing together.

### Authorization gates

Separate gates for S3, CloudFront, ALB/HTTPS API resources, RDS, ECS update, task-role IAM, security groups, Entra redirect, Gmail callback.

### Cost gates

RDS is **material**. ALB is **standing hourly cost** while retained. CloudFront/S3 are usage. ECS can stay at `desiredCount=0` when idle; ALB still bills.

### Live validation boundary

Browser MSAL against the CloudFront API. Live Gmail and Bedrock wait for 16E. No Send. Never send a real bearer token to task-IP HTTP.

### Expected tests

Offline regression; HTTPS smoke through CloudFront. No Bedrock invoke in 16D.

### Exit criteria

SPA and API HTTPS hostnames live without custom domain; ECS registered behind ALB; RDS migrated; Secrets Manager backend selected; CORS/`FRONTEND_OAUTH_RETURN_URL` set to the SPA CloudFront origin.

---

## 16E — AWS Live Mailbox → Amazon Bedrock Validation

**Status: Not started.**

### Objective

Prove Gmail mailbox → Bedrock analyze → propose → approve on AWS. Stop before Send.

### Planned cloud mutations

None required if 16D is complete. Optional: one Bedrock invoke. Desired count may be raised then returned to 0.

### Authorization gates

Live Gmail OAuth; live Bedrock inference. Each separate.

### Cost gates

Bedrock: **one** selected-message real analysis unless an explicit retry is required. Avoid repeated calls.

### Live validation boundary

Gmail on AWS only. Not Graph. Not Send. Not Foundry.

### Expected tests

Controlled live path; credentials survive task restart without normal reauthorization.

### Exit criteria

Same product path as 16C with Gmail + Bedrock. Stop before Send.

---

## 16F — Cross-Cloud Parity / Security / Cost Hardening + Final Documentation

**Status: Not started.**

### Objective

Reconcile documentation, confirm parity of the two proofs, and apply cost hardening (stop databases, scale compute to zero, optionally delete ALB).

### Planned cloud mutations

Stop/start or delete only under explicit gates. Never delete `rg-eci-dev`. Do not delete Key Vault/Foundry/ACR/ECS cluster as part of “cleanup” unless a later prompt explicitly says so.

### Authorization gates

Any stop, delete, or ingress tighten-back.

### Cost gates

Do not keep two managed PostgreSQL servers running for symmetry. ALB is the main AWS standing-cost leftover after compute scale-to-zero.

### Live validation boundary

No additional live Send. No extra AI calls unless a documented defect requires one authorized retry.

### Expected tests

Full offline regression. README/docs reconciliation.

### Exit criteria

Parity notes, cost state recorded, ADR/roadmap/README consistent, no silent billable leftovers undocumented.

---

## Azure current resource inventory (16A, sanitized)

| Resource | Current state | Reuse? | Mutation later? | Cost relevance | Notes |
|---|---|---|---|---|---|
| `rg-eci-dev` | Exists, Spain Central | REUSE | No | Foundry | Never delete |
| `rg-eci-deploy-dev` | Exists, Spain Central | REUSE | No | Deploy RG | |
| ACR `eciacrdev6c` | Basic; tags `dd55327`/`stable`/historical | REUSE | Push current image | Low | Phase 8 image, not current `master` |
| UAMI `eci-ca-identity-dev` | Attached to ACA | REUSE | Key Vault RBAC | None | AcrPull + Foundry User; **no Key Vault role** |
| `eci-github-deploy-dev` (Azure) | Exists | REUSE | No | None | CD identity |
| LAW `eci-law-dev` | 30-day | REUSE | No | Low ingest | CAE destination |
| CAE `eci-ca-env-dev` | Succeeded | REUSE | No | Standing env | |
| ACA `eci-api-dev` | Rev `eci-api-dev--0000003`, ScaledToZero | REUSE | Image, env, ingress | Usage when up | Image `dd55327`; external HTTPS; operator `/32`; min 0 / max 1 |
| Foundry `eci-foundry-dev-susanta` / `eci-project-dev` / `eci-gpt-54-mini` | Succeeded | REUSE | No create | Inference later | Not invoked in 16A |
| Key Vault `eci-kv-oauth-dev-susanta` | Standard, RBAC on | REUSE | UAMI RBAC | Low | Secret values not read |
| Azure PostgreSQL | **None** | CREATE LATER | Create in 16B | Material | |
| Azure Static Web Apps | **None** | CREATE LATER | Create in 16B | Low/usage | |
| Entra `eci-web-dev` | SPA redirect `http://localhost:5173` only | REUSE | Add HTTPS redirect | None | |
| Entra `eci-api-auth-dev` | Five delegated scopes present | REUSE | No new app | None | |

ACA env **names** present: `AI_PROVIDER`, `APP_ENV`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT`, `AZURE_CLIENT_ID`, `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_REQUIRED_PERMISSION`.

Missing for Phase 16: `DATABASE_URL`, `CREDENTIAL_STORE_BACKEND`, `AZURE_KEY_VAULT_URL`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_OAUTH_RETURN_URL`, Gmail OAuth, Microsoft mailbox OAuth.

---

## AWS current resource inventory (16A, sanitized)

Identity: IAM user `eci-developer`, account `034456343525`, region `eu-south-2`. No mutation.

| Resource | Current state | Reuse? | Mutation later? | Cost relevance | Notes |
|---|---|---|---|---|---|
| ECR `eci-api-dev` | Exists; tags `dd55327`/`stable`/historical | REUSE | Push current image | Low | Same digest family as ACR Phase 8 |
| Cluster `eci-cluster-dev` | ACTIVE | REUSE | No | Low | 0 running tasks |
| Service `eci-api-dev` | desiredCount 0 / running 0 | REUSE | Task def, LB attach, env | Usage when up | `eci-api-dev:4`; `loadBalancers: []`; public IP enabled |
| Task def `eci-api-dev:4` | Image `dd55327` | UPDATE LATER | Env + image | None | See env names below |
| Execution role `eci-ecs-execution-role-dev` | `AmazonECSTaskExecutionRolePolicy` | REUSE | No | None | Image pull + logs |
| Task role `eci-bedrock-task-role-dev` | Inline `bedrock:InvokeModel` only | UPDATE LATER | Secrets Manager IAM | None | No SM permissions; no `ListSecrets` (correct to omit) |
| Log group `/ecs/eci-api-dev` | 1-day retention | REUSE | No | Low | Log bodies not inspected |
| SG `eci-fargate-sg-dev` | TCP 8000 operator `/32` | UPDATE LATER | Ingress for ALB | None | Incompatible with public OAuth/browser as sole rule |
| ALB / target group | Not attached to service | CREATE LATER | 16D | **Standing hourly** | ELB describe APIs denied to `eci-developer`; ECS `loadBalancers` empty; Phase 8B teardown still the operational fact |
| RDS PostgreSQL | Not in task config | CREATE LATER | 16D | Material | `rds:Describe*` denied to `eci-developer`; no `DATABASE_URL` on the task |
| Secrets Manager | Namespace supported in code | UPDATE LATER | Task-role IAM | Low/usage | `ListSecrets` denied (and not required). Values not read. 13E validated developer identity, not the task role |
| S3 frontend bucket | None known | CREATE LATER | 16D | Low | `s3:ListAllMyBuckets` denied |
| CloudFront | None known | CREATE LATER | 16D | Usage | `cloudfront:ListDistributions` denied |
| Bedrock profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | ACTIVE in `eu-south-2` | REUSE | No | Inference later | Not invoked |
| GitHub role `eci-github-deploy-dev` | Documented; inspect denied | REUSE | Maybe extra CD perms later | None | `iam:GetRole` denied to `eci-developer` (same as Phase 8) |

Task env **names** present: `AI_PROVIDER`, `APP_ENV`, `BEDROCK_REGION`, `BEDROCK_MODEL_ID`, `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_REQUIRED_PERMISSION`.

Missing: `DATABASE_URL`, credential store, CORS, OAuth return, Gmail/Microsoft OAuth.

---

## Resource-create matrix (later; none in 16A)

| Future resource | Purpose | Reuse alternative | Why new | Cost class | Stop / scale-to-zero | Cleanup | Data loss if deleted | Future authorization phrase |
|---|---|---|---|---|---|---|---|---|
| Azure Static Web Apps | Azure SPA HTTPS | None | No SWA exists | Low / usage | N/A (static) | Delete SWA | SPA files only | `BLOCKED — USER AUTHORIZATION REQUIRED` — create Azure Static Web App |
| Azure PostgreSQL Flexible Server | Azure durable state | None | No server exists | Material | Stop compute; storage may still bill | Delete server | **Yes — database** | `BLOCKED — USER AUTHORIZATION REQUIRED` — create Azure PostgreSQL Flexible Server |
| AWS S3 SPA bucket | CloudFront origin | None | No ECI frontend bucket | Low | N/A | Empty + delete bucket | SPA files | `BLOCKED — USER AUTHORIZATION REQUIRED` — create S3 frontend bucket |
| CloudFront SPA distribution | SPA HTTPS hostname | None | No distribution | Usage | Disable distribution | Delete distribution | Hostname gone | `BLOCKED — USER AUTHORIZATION REQUIRED` — create CloudFront SPA distribution |
| CloudFront API distribution | API HTTPS without custom domain | None | No distribution | Usage | Disable | Delete | API hostname gone | `BLOCKED — USER AUTHORIZATION REQUIRED` — create CloudFront API distribution |
| ALB + TG + HTTP listener | Stable ECS origin for CloudFront | Historical TG name not attached | Required; CF cannot target tasks | **Standing hourly** | Cannot scale to zero | Delete ALB/TG (Phase 8B pattern) | No app DB | `BLOCKED — USER AUTHORIZATION REQUIRED` — create AWS API HTTPS ALB path |
| Amazon RDS PostgreSQL | AWS durable state | None | No RDS in task config | Material | Stop instance; storage may still bill | Delete instance | **Yes — database** | `BLOCKED — USER AUTHORIZATION REQUIRED` — create Amazon RDS PostgreSQL |

Authorization phrase must include the nine-point cost-gate report.

---

## Azure backend environment matrix

Classification: **public identifier** / **secret** / **runtime URL** / **derived** / **cloud identity**.

Do not put real secrets in docs or Git.

| Variable | Azure production value / source | Class |
|---|---|---|
| `APP_ENV` | `production` | public identifier |
| `AUTH_MODE` | `oidc` | public identifier |
| `OIDC_ISSUER` | `https://login.microsoftonline.com/<tenant-id>/v2.0` | runtime URL |
| `OIDC_AUDIENCE` | `eci-api-auth-dev` application ID | public identifier |
| `OIDC_JWKS_URL` | `https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys` | runtime URL |
| `OIDC_REQUIRED_PERMISSION` | `communications:analyze` (per-route permissions still apply) | public identifier |
| `DATABASE_URL` | `postgresql+psycopg://…` to Flexible Server | secret (password) + runtime URL |
| `AI_PROVIDER` | `microsoft_foundry` | public identifier |
| `FOUNDRY_PROJECT_ENDPOINT` | existing project endpoint | runtime URL |
| `FOUNDRY_MODEL_DEPLOYMENT` | `eci-gpt-54-mini` | public identifier |
| `AZURE_CLIENT_ID` | UAMI `eci-ca-identity-dev` client ID (SDK env; not a Settings field) | cloud identity |
| `CREDENTIAL_STORE_BACKEND` | `azure_key_vault` | public identifier |
| `AZURE_KEY_VAULT_URL` | `https://eci-kv-oauth-dev-susanta.vault.azure.net` | runtime URL |
| `GMAIL_OAUTH_CLIENT_ID` | existing Google OAuth client | public identifier |
| `GMAIL_OAUTH_CLIENT_SECRET` | secret reference / ACA secret — never in Git | secret |
| `GMAIL_OAUTH_REDIRECT_URI` | `https://<aca-host>/api/v1/oauth/callbacks/gmail` | runtime URL |
| `MICROSOFT_OAUTH_CLIENT_ID` | existing Graph mailbox app | public identifier |
| `MICROSOFT_OAUTH_CLIENT_SECRET` | secret reference — never in Git | secret |
| `MICROSOFT_OAUTH_REDIRECT_URI` | `https://<aca-host>/api/v1/oauth/callbacks/microsoft_graph` | runtime URL |
| `MICROSOFT_OAUTH_TENANT` | existing tenant alias or GUID | public identifier |
| `CORS_ALLOWED_ORIGINS` | `https://<azure-swa-host>` and optional `http://localhost:5173` | runtime URL |
| `FRONTEND_OAUTH_RETURN_URL` | `https://<azure-swa-host>` (fixed; never from query) | runtime URL |

Gmail requested scopes (code, not Settings): `openid`, `gmail.readonly`, `gmail.send`.

Microsoft requested scopes (code, not Settings): `openid`, `profile`, `offline_access`, `Mail.Read`, `Mail.Send`.

---

## AWS backend environment matrix

Runtime identity is the ECS task role. Do not set static AWS keys on the task.

| Variable | AWS production value / source | Class |
|---|---|---|
| `APP_ENV` | `production` | public identifier |
| `AUTH_MODE` | `oidc` | public identifier |
| `OIDC_ISSUER` | same Entra issuer as Azure | runtime URL |
| `OIDC_AUDIENCE` | same `eci-api-auth-dev` | public identifier |
| `OIDC_JWKS_URL` | same JWKS as Azure | runtime URL |
| `OIDC_REQUIRED_PERMISSION` | `communications:analyze` | public identifier |
| `DATABASE_URL` | `postgresql+psycopg://…` to RDS | secret + runtime URL |
| `AI_PROVIDER` | `amazon_bedrock` | public identifier |
| `BEDROCK_REGION` | `eu-south-2` | public identifier |
| `BEDROCK_MODEL_ID` | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | public identifier |
| `CREDENTIAL_STORE_BACKEND` | `aws_secrets_manager` | public identifier |
| `AWS_SECRETS_MANAGER_REGION` | `eu-south-2` | public identifier |
| `AWS_SECRETS_MANAGER_NAMESPACE` | `eci/mailbox-oauth` (default) | public identifier |
| Gmail OAuth trio | same client as local; callback on API CloudFront HTTPS | identifier + secret + runtime URL |
| Microsoft OAuth quartet | configured if the AWS API must accept Graph callbacks; live matrix does not require Graph on AWS | identifier + secret + runtime URL |
| `CORS_ALLOWED_ORIGINS` | `https://<aws-spa-cloudfront-host>` and optional localhost | runtime URL |
| `FRONTEND_OAUTH_RETURN_URL` | `https://<aws-spa-cloudfront-host>` | runtime URL |

---

## Frontend build matrices

Same variable names. Same five full scope identifiers against `eci-api-auth-dev`. Different API base and redirect origin.

| Variable | Azure build | AWS build |
|---|---|---|
| `VITE_ECI_API_BASE_URL` | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io` | `https://<aws-api-cloudfront-host>` |
| `VITE_ENTRA_TENANT_ID` | same tenant | same tenant |
| `VITE_ENTRA_SPA_CLIENT_ID` | `eci-web-dev` | `eci-web-dev` |
| `VITE_ENTRA_REDIRECT_URI` | `https://<azure-swa-host>` | `https://<aws-spa-cloudfront-host>` |
| `VITE_ECI_API_SCOPES` | `api://<eci-api-client-id>/communications:read,analyze,connect,workflow,send` (full identifiers) | same identifiers |

---

## Redirect / CORS matrix

| Row | LOCAL | AZURE | AWS |
|---|---|---|---|
| MSAL SPA redirect | `http://localhost:5173` | `https://<azure-swa-host>` | `https://<aws-spa-cloudfront-host>` |
| Gmail provider callback | `http://localhost:8000/api/v1/oauth/callbacks/gmail` | `https://<aca-host>/api/v1/oauth/callbacks/gmail` | `https://<aws-api-cloudfront-host>/api/v1/oauth/callbacks/gmail` |
| Microsoft mailbox callback | `http://localhost:8000/api/v1/oauth/callbacks/microsoft_graph` | `https://<aca-host>/api/v1/oauth/callbacks/microsoft_graph` | `https://<aws-api-cloudfront-host>/api/v1/oauth/callbacks/microsoft_graph` if that cloud must accept Graph callbacks |
| `FRONTEND_OAUTH_RETURN_URL` | `http://localhost:5173` | `https://<azure-swa-host>` | `https://<aws-spa-cloudfront-host>` |
| CORS origin (that cloud’s API) | `http://localhost:5173` | SWA origin + optional localhost | SPA CloudFront origin + optional localhost |

CORS remains an explicit allowlist, no wildcard, `allow_credentials=false`. Each cloud API should allow **its matching SPA origin** plus localhost if local development is retained — not every deployed SPA origin.

---

## Ingress

### Azure (current → later)

Current: external HTTPS, `allowInsecure=false`, operator `/32`. That blocks browsers and Google/Microsoft OAuth redirects.

Later 16B: public ACA HTTPS. Application OIDC is the primary access control. Do not mutate in 16A.

### AWS (current → later)

Current: no ALB on the service; Fargate public IP; SG TCP 8000 operator `/32`; HTTP only. Unsafe for real bearer tokens (ADR-010).

Later 16D: CloudFront HTTPS → ALB HTTP → ECS. Fargate SG allows ALB. ALB SG allows CloudFront prefix list. Task-IP HTTP remains verification-only if it still exists.

---

## IAM / RBAC gap matrix

| Identity | Need | Current | Gap |
|---|---|---|---|
| Azure UAMI | AcrPull | Present | None |
| Azure UAMI | Foundry User | Present | None |
| Azure UAMI | Key Vault secrets data plane | **Missing** | Add Secrets User (or equivalent) in 16B |
| AWS execution role | ECR pull + awslogs | Present | None |
| AWS task role | `bedrock:InvokeModel` on Haiku EU profile | Present | None |
| AWS task role | Secrets Manager on `eci/mailbox-oauth/*`: CreateSecret, GetSecretValue, PutSecretValue, UpdateSecretVersionStage, DescribeSecret, DeleteSecret | **Missing** | Add in 16D; do **not** add `ListSecrets`; add KMS only if the namespace is CMK-encrypted |
| AWS GitHub deploy role | Existing ECR/ECS deploy | Documented; not inspectable by `eci-developer` | Extra S3/CloudFront deploy perms only if CD should upload the SPA |

---

## AI live-call cost gate

| Slice | Provider | Policy |
|---|---|---|
| 16C | Microsoft Foundry | One selected-message analysis unless one explicit retry after failure |
| 16E | Amazon Bedrock | One selected-message analysis unless one explicit retry after failure |

Do not call either in 16A.

---

## PostgreSQL strategy

- Version: **PostgreSQL 16** (CI image `postgres:16`).
- Azure: Flexible Server in Spain Central, TLS required, firewall/VNet so ACA can connect.
- AWS: RDS PostgreSQL in the ECS VPC, TLS required, SG from `eci-fargate-sg-dev`.
- Credentials: injected `DATABASE_URL`; do not commit passwords. Entra/IAM DB auth remains future (ADR-014).
- Migration: `alembic upgrade head` once per new database. Current head: **`13a0001`**. No new revision in 16A.
- Advisory locks: required for durable credential mutations (`pg_advisory_xact_lock`).
- Sequential: Azure proof first, then stop/pause Azure PG before RDS (or reverse) so both are not standing indefinitely.

Database cost gates: both are mandatory for a credible cloud proof; no reusable server exists; cost class potentially material; stop may still bill storage; delete destroys data; later create prompts must stop before create.

---

## CI/CD plan

Current: `.github/workflows/ci.yml` (automatic tests, including frontend); `.github/workflows/deploy.yml` (`workflow_dispatch` azure/aws/both; backend image only).

Phase 16 recommendation (implement in 16B/16D, not 16A):

- Keep **manual** `workflow_dispatch`. Do not auto-deploy on push.
- Extend the existing deploy workflow with optional frontend jobs rather than a second CD product.
- Backend: build current image, push ACR/ECR, update ACA/ECS, apply env safely, run `alembic upgrade head` once against the new DB (not from every replica startup).
- Frontend: Azure production Vite build + SWA deploy; AWS production Vite build + S3 sync + CloudFront invalidation.

---

## IaC decision

**No.** Phase 16 does not introduce Terraform, Bicep, CDK, or CloudFormation.

---

## Mailbox OAuth client reuse

Reuse existing development Google and Microsoft mailbox OAuth apps. Later add cloud HTTPS redirect URIs; keep local HTTP callbacks. Do not create new OAuth applications unless a provider refuses additional URIs. No provider mutation in 16A.

---

## Application-code review (16A)

- Backend: **no change required.** Gaps are configuration, RBAC, ingress, and hosting.
- Frontend: **no change required.** Per-environment Vite builds are sufficient. Runtime config JSON and cloud selectors are out of scope.
- Alembic: **no new revision.** Head remains `13a0001`.

---

## Future Azure authorization gates (not 16A)

1. ACA image/config update
2. ACA ingress change
3. Static Web App creation
4. Azure PostgreSQL creation
5. Key Vault RBAC mutation
6. Entra SPA redirect addition
7. Gmail cloud callback addition
8. Microsoft mailbox callback addition
9. Live Graph mailbox OAuth
10. Live Foundry inference

## Future AWS authorization gates (not 16A)

1. S3 creation
2. CloudFront creation (SPA and API)
3. ALB / API HTTPS resource creation
4. RDS creation
5. ECS task definition / service update
6. Task-role Secrets Manager permission mutation
7. Security-group mutation
8. Entra SPA redirect addition
9. Gmail callback addition
10. Microsoft callback addition if needed
11. Live Gmail OAuth
12. Live Bedrock inference

---

## Deliberate Phase 16 non-goals

- Live Send / execute as an exit criterion
- 2×2×2 cloud × AI × mailbox matrix
- Custom domains
- Duplicate Entra or mailbox OAuth apps
- In-memory credential store on cloud
- Shared cross-cloud PostgreSQL
- IaC platform
- Automatic CD
- Runtime frontend cloud switcher
- Deleting `rg-eci-dev`
