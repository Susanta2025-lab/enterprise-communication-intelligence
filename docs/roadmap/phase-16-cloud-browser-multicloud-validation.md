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

Phase 16A is **Completed**. Phase 16B is **Completed**. Phase 16C is **Completed**. Phase 16D is **COMPLETE / PASS**. Phase 16E is **Next** (not started). Phase 16F is **Not started**.

- **16A is Completed:** authenticated read-only Azure and AWS inventory; topology freeze; ADR-026; configuration/cost/authorization matrices; offline regression. No cloud mutation.
- **16B is Completed:** Azure SWA + current-master ACA + PostgreSQL 16 + Key Vault backend + Entra/MSAL browser smoke. No mailbox live proof. No Foundry inference. No Send.
- **16C is Completed:** Azure Graph delegated OAuth → Key Vault durability across ACA recycle → one MicrosoftFoundryProvider selected-message Analyze → explicit Propose (PENDING) → explicit Approve (APPROVED). STOP before Send.
- **16D is COMPLETE / PASS:** AWS HTTPS SPA/API, RDS, Secrets Manager backend, Entra/MSAL, CORS, and protected browser APIs. Corrective connector-list 503 resolved. No Gmail, Graph mailbox, Bedrock inference, or Send.
- **16E is Next (not started):** AWS live mailbox → Amazon Bedrock validation.
- **16F is Not started:** cross-cloud parity, security/cost hardening, temporary IAM cleanup, final documentation.

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

Azure SPA origin (16B): `https://witty-island-03f5de51e.7.azurestaticapps.net`

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

SPA origin (16D): `https://d1ut7j94w7lt3b.cloudfront.net`

API origin (16D): `https://dnookm0ucbhv1.cloudfront.net`

Custom domain: **not required**. SPA and API use **separate** CloudFront distributions. S3 origin is private (OAC; no static website hosting).

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

**Status: Completed.**

Baseline commit: `75183601e9e82c55650363456aa8a863fc64d992` (Phase 16A docs; GitHub CI green).

### Objective

Host the Azure SPA on Static Web Apps and run current `master` on ACA with PostgreSQL, Key Vault, CORS, and OAuth return — reachable by browser and OAuth callbacks over HTTPS.

### Result

HTTPS Azure SPA → Entra/MSAL (`eci-web-dev`) → ACA HTTPS → Azure PostgreSQL → Key Vault configured (not invoked for mailbox OAuth) → protected `GET /api/v1/analyses?limit=1`. Empty connector dashboard is expected (clean cloud database). No mailbox OAuth consent. No Foundry inference. No Send.

### Deployed resources

| Resource | Result |
|---|---|
| ACR image | `eciacrdev6c.azurecr.io/eci-api:7518360` (immutable SHA; `stable` not overwritten) |
| ACA | `eci-api-dev` revision `eci-api-dev--0000004`; min 0 / max 1; HTTPS only; public ingress; OIDC retained |
| SWA | `eci-web-dev` in `rg-eci-deploy-dev`; Free SKU; control-plane West US 2 (Spain Central is not a SWA region; West Europe rejected new customers) |
| SWA hostname | `https://witty-island-03f5de51e.7.azurestaticapps.net` |
| PostgreSQL | `eci-pg-dev-susanta`; version 16; Burstable `Standard_B1ms`; 32 GiB; HA off; Spain Central; TLS `require_secure_transport=on` |
| Alembic | existing chain to head `13a0001`; no new revision |
| Key Vault RBAC | runtime UAMI `eci-ca-identity-dev`: **Key Vault Secrets Officer** (get/set/delete required; Secrets User is read-only) |
| Credential store | `CREDENTIAL_STORE_BACKEND=azure_key_vault` |
| CORS / OAuth return | SWA origin only |
| Entra SPA | `eci-web-dev` redirects: `http://localhost:5173` + SWA HTTPS |
| Mailbox callbacks | ACA HTTPS Gmail and Microsoft Graph URIs registered; localhost preserved; unused in 16B |

Firewall for PostgreSQL is public-access with `/32` rules for ACA outbound and operator migration only. Not `0.0.0.0/0`. Not blanket Allow Azure services.

### Live validation boundary

Browser MSAL against ACA passed. Live mailbox OAuth and Foundry inference wait for 16C. No Send.

### Cost state after 16B

Retained: ACR Basic (standing), ACA Consumption min=0 (usage), LAW (low ingest), Key Vault (low), Foundry (not invoked). New: SWA Free (no standing SKU charge; bandwidth quota), PostgreSQL Flexible Server **material** (compute while running; storage continues if stopped; auto-starts after 7 days stopped). Do not stop/delete for 16C. `rg-eci-dev` unchanged.

---

## 16C — Azure Live Mailbox → Microsoft Foundry Validation

**Status: Completed.**

Baseline commit: `f19dba6280d58dd364058728ee7f3987c7fe1e8f` (Phase 16B closure; GitHub CI green).

### Objective

Prove Graph mailbox → Foundry analyze → propose → approve on Azure. Stop before Send.

### Result

Azure-hosted path:

```text
Azure Static Web Apps
→ Entra/MSAL
→ Azure Container Apps
→ Azure PostgreSQL
→ Azure Key Vault
→ Microsoft Graph
→ MicrosoftFoundryProvider
→ Analyze
→ Propose
→ Approve
→ STOP before Send
```

Sanitized live proof:

- Real Microsoft Graph delegated OAuth completed.
- Graph `ConnectorAccount` remained **ACTIVE**.
- Delegated credentials stored via Azure Key Vault (`CREDENTIAL_STORE_BACKEND=azure_key_vault`).
- Initial bounded Graph list `page_size=10` passed.
- ACA same-revision process/replica recycle occurred (same image, environment, ingress, scale, and UAMI; revision `eci-api-dev--0000004`).
- Post-recycle ACA health/readiness passed.
- Post-recycle Graph list passed with **no reauthorization**.
- Durable delegated credential behavior proven: OAuth → credential persistence → Graph list → ACA same-revision restart → Graph list → no reauthorization.
- Exactly one selected-message Analyze passed through real `MicrosoftFoundryProvider` and the existing Foundry deployment `eci-gpt-54-mini`.
- `MockAIProvider` was **not** used.
- Exactly one Foundry inference.
- Explicit Propose created exactly one `WorkflowAction` in **PENDING**.
- Explicit Approve transitioned the same action to **APPROVED**.
- Approval provenance confirmed from ACA/Log Analytics: one `POST` approve, `workflow_action_approved`, HTTP 200; no second approve.
- Execute/send request count remained **zero**. Live Send was **not** performed.
- Gmail unused. Amazon Bedrock unused. AWS unused.
- No cloud resource created or deleted in 16C.
- No application-code change. No Alembic revision. Schema head remains `13a0001`.

The authorized browser Approve action completed successfully server-side even though the Cursor/browser automation appeared stalled afterward. ACA telemetry proved **PENDING → APPROVED** with HTTP 200.

AI draft ≠ workflow proposal ≠ approved communication ≠ sent communication. The Send button may become eligible after **APPROVED**; Phase 16C did not execute it.

This is not geo redundancy, disaster recovery, Key Vault outage resilience, multi-replica race certification, credential-rotation certification, Foundry load/throughput/quality benchmarking, multiple-message certification, Gmail→Foundry cloud certification, or Foundry retry/reconciliation.

### Frontend presentation-state observation

Mailbox analysis and workflow-card presentation is browser-memory state. An SPA remount caused the displayed analysis/workflow card to disappear. The persisted `WorkflowAction` remained durable in Azure PostgreSQL and was recoverable through existing read APIs. No second analysis or Foundry call was required. No backend persistence defect occurred. This is **not data loss**. Workflow-history/recovery UI is a deliberate post-Phase-16 frontend enhancement / known UX limitation. Phase 16C did not add that UI.

### Planned cloud mutations

None. Optional Foundry: exactly one selected-message inference (consumed). No Send.

### Authorization gates

Completed: live Microsoft mailbox OAuth; one live Foundry inference; explicit Propose; explicit Approve. Each was a separate gate. Send/execute was not authorized.

### Cost gates

Foundry: **one** selected-message real analysis. No retry. No additional AI call during closure.

### Live validation boundary

Microsoft Graph mailbox on Azure only. Not Gmail. Not Send. Not Bedrock. Not AWS.

### Expected tests

Offline focused and full frontend/backend regression. No live Azure/Graph/Foundry calls during 16C documentation closure.

### Offline regression (16C closure)

- Focused frontend (MSAL/auth, connector dashboard, mailbox workspace, Analyze, Propose/Approve/Send safety): 11 files, **154 passed**
- Full frontend: `npm ci`; typecheck pass; lint pass; **182 passed** (18 files); production build pass (chunk-size advisory on the existing SPA bundle; not a 16C defect)
- Focused backend (OIDC/scopes, Graph OAuth, identity matching, credential store/Key Vault fakes, token refresh, connector lifecycle, bounded Graph listing, mailbox analyze, Foundry factory, analysis/workflow persistence, approve, execute-not-called, privacy/logging): **789 passed**
- Local PostgreSQL (`tests/postgres` against existing disposable `eci_test`; not Azure production): **82 passed**
- Full backend `python -m pytest`: **1947 passed**, 82 skipped (PostgreSQL suite skipped without the test URL in the default run)
- `python -m pip check`: no broken requirements
- `python -m ruff check .`: all checks passed
- `git diff --check`: recorded after documentation edits

No application-code change. No Alembic revision. Schema head remains `13a0001`.

### Cost state after 16C

No new resources. PostgreSQL Flexible Server remained running (do **not** stop in this closure; sequential database/cost handling belongs before or during 16D under a separate authorization gate). SWA Free. ACA normal runtime plus one same-revision recycle. Key Vault normal operations. Graph normal provider usage. Exactly one Foundry inference; no additional AI retry.

### Exit criteria

Delegated Graph credentials persist across ACA replica recycle without normal reauthorization; one Foundry mailbox analysis via `MicrosoftFoundryProvider`; Propose → PENDING → Approve → APPROVED; stop before Send; offline regression green. Working tree left unstaged/uncommitted.

---

## 16D — AWS HTTPS + Full-Stack Browser Deployment

**Status: COMPLETE / PASS.**

Corrective runtime commit: `0050b30c31d1fc925b19532e177c76e48494b745` (`fix: decouple connector listing from oauth store`; GitHub CI all green).

### Objective

Host the AWS SPA on private S3 + CloudFront OAC and run current `master` on ECS/Fargate behind CloudFront HTTPS → HTTP ALB, with colocated RDS PostgreSQL, AWS Secrets Manager as the mailbox credential-store backend, CORS, and Entra/MSAL — reachable by browser over HTTPS without a custom domain.

### Result

HTTPS AWS SPA → Entra/MSAL (`eci-web-dev`) → API CloudFront HTTPS → HTTP ALB :80 → ECS/Fargate :8000 → Amazon RDS PostgreSQL → AWS Secrets Manager configured (not invoked for mailbox OAuth) → protected `GET /api/v1/analyses?limit=1` and `GET /api/v1/connector-accounts`. Empty Gmail/Outlook connector cards are expected (no AWS mailbox connector configured). No mailbox OAuth consent. No Bedrock inference. No Analyze / Propose / Approve / Reject / Send.

Validated browser request path:

```text
SPA CloudFront HTTPS
→ API CloudFront HTTPS
→ ALB HTTP:80
→ ECS/Fargate :8000
→ PostgreSQL
```

Authentication path:

```text
Browser
→ Microsoft Entra / MSAL
→ delegated ECI API access token
→ API CloudFront
→ FastAPI OIDC validation
```

This is hosting, browser authentication, protected API transport, CORS, persistence, and frontend/backend integration. It is **not** the Phase 16E real mailbox + Bedrock proof.

### Deployed resources

Region: `eu-south-2`.

| Resource | Result |
|---|---|
| ECR | `eci-api-dev`; immutable tag `0050b30`; digest `sha256:d2e8f50738729033ca58a390ca490a95c7a51f9944316e600eecfb14d3c46316`; historical images retained |
| Deployed application commit | `0050b30c31d1fc925b19532e177c76e48494b745` |
| ECS cluster | `eci-cluster-dev` |
| ECS service | `eci-api-dev` |
| Final task definition | `eci-api-dev:6` |
| Desired / running / pending | 1 / 1 / 0 |
| PRIMARY deployment | COMPLETED |
| Target group | `eci-api-tg-dev`; exactly one registered target; **HEALTHY** |
| API CloudFront | `E2IF9K4FM4A6WJ`; `https://dnookm0ucbhv1.cloudfront.net` |
| API health | `GET /health` 200; `GET /api/v1/readiness` 200 |
| ALB | `eci-alb-dev`; HTTP origin path to ECS; CloudFront is the public HTTPS boundary |
| RDS | identifier `eci-pg-dev`; PostgreSQL 16.15; database `eci`; runtime role `eci_app` |
| Alembic | existing chain to head `13a0001`; no new revision |
| `DATABASE_URL` | ECS secret reference only; plaintext `DATABASE_URL` absent from task environment |
| Credential store | `CREDENTIAL_STORE_BACKEND=aws_secrets_manager`; production in-memory store forbidden |
| S3 SPA bucket | `eci-web-aws-dev-034456343525`; private; all four Block Public Access controls enabled; website hosting not configured |
| OAC | `eci-spa-oac-dev`; CloudFront OAC is the only origin access path |
| SPA CloudFront | `E1XFNK98P7PU2W`; `https://d1ut7j94w7lt3b.cloudfront.net` |
| SPA routes | root `/` 200; SPA fallback `/connectors` 200 |
| SPA publish | production `frontend/dist/` only; five build objects; secret-material scan PASS / absent; invalidation `IARJ17FW0LSTJQ5ITFCE02AHC5` Completed |
| Entra SPA | `eci-web-dev` client ID `504c786d-1b61-4650-9cf9-6ee1b565140b` |
| Entra API | `eci-api-auth-dev` app/client ID `57109f68-2e3a-4fab-af54-31846343f7a2` |
| Entra SPA redirects | localhost `http://localhost:5173`; Azure SPA `https://witty-island-03f5de51e.7.azurestaticapps.net`; AWS SPA `https://d1ut7j94w7lt3b.cloudfront.net` (added while preserving existing redirects) |
| CORS | exact origin `https://d1ut7j94w7lt3b.cloudfront.net` on API `https://dnookm0ucbhv1.cloudfront.net`; wildcard absent |

Runtime IAM (permanent; not 16D cleanup candidates): `eci-mailbox-secrets-runtime-dev` on the ECS task role; `eci-runtime-db-secret-execution-dev` on the ECS execution role. Task role and execution role remain separate. No static AWS credentials on the task.

S3 remained private. Its OAC and Block Public Access security posture was preserved.

No custom domain. No in-app cloud switcher. Same `frontend/` source; AWS environment Vite build.

### Entra / MSAL / CORS proof

Delegated ECI API permissions (explicit; `.default` not used):

- `communications:read`
- `communications:analyze`
- `communications:connect`
- `communications:workflow`
- `communications:send`

MSAL browser login **PASS**. Redirect returned to the AWS SPA. No redirect loop. Expected ECI API audience validated. Bearer token values were never printed.

CORS preflight `OPTIONS` **200** with exact `Access-Control-Allow-Origin` equal to the AWS SPA origin. Authenticated browser request **PASS**.

### Protected browser proof

| Request | Result |
|---|---|
| `GET /api/v1/analyses?limit=1` | 200 |
| `GET /api/v1/connector-accounts?limit=20&offset=0` | 200 (after corrective redeploy) |

Final connector dashboard rendered normally. No 503 product error. Empty Gmail/Outlook connector cards were acceptable because no AWS mailbox connector had been configured.

Phase 16D did **not** validate real Gmail access, Microsoft Graph mailbox access, or Bedrock inference.

### Gate J runtime deployment incident

Initial runtime deployment used task definition `eci-api-dev:5`. The new task was healthy and registered in the target group.

Unexpected condition (not a normal deployment requirement):

- service `desiredCount` = 1
- two tasks remained running
- the historical revision-4 task belonged to the previous ECS service deployment; it was **not** an orphan `RunTask`
- old deployment desired count had become 0
- old task was not registered in the target group
- PRIMARY remained `IN_PROGRESS`
- bounded natural-drain observation did not resolve it

Read-only diagnosis classified: `SERVICE ROLLOUT BLOCKED — CONFIGURATION DECISION REQUIRED`.

After explicit authorization, exactly one `ecs:StopTask` was issued for the exact old revision-4 task. The new revision-5 task was not stopped. No rollback occurred. No replacement revision-4 task appeared. Final state became 1 / 1 / 0. PRIMARY completed. Target remained healthy. API health/readiness remained 200.

This was an observed ECS rollout anomaly handled with bounded, least-privilege intervention. During the later corrective image deployment (`eci-api-dev:6`), the old ALB target drained naturally and **no** additional `StopTask` was required.

### Gate K connector-list defect

Initial authenticated browser result:

`GET /api/v1/connector-accounts?limit=20&offset=0` → **503**

Authentication had already succeeded. Root cause: the GET metadata route was incorrectly composed through the connector connect/lifecycle dependency:

```text
GET connector list
→ get_connector_account_service
→ communications:connect lifecycle construction
→ require_shared_oauth_store
```

Without configured Gmail or Microsoft mailbox OAuth provider settings, that lifecycle dependency reported the store unavailable.

`ConnectorAccountService.list_owned()` only requires authenticated identity and PostgreSQL persistence. It does not need credential-store access, Gmail, Microsoft Graph, mailbox OAuth, or token refresh.

Corrective implementation introduced `get_connector_account_listing_service`:

```text
GET connector list
→ communications:read
→ persistence only
```

Preserved security: disconnect remains `communications:connect`; reauthorize remains `communications:connect`; lifecycle credential-store requirements remain intact; production memory-store prohibition remains intact.

Corrective commit: `0050b30c31d1fc925b19532e177c76e48494b745` — `fix: decouple connector listing from oauth store`.

Focused tests: **72 passed** (connector-list 8, lifecycle 7, dependency 48, OAuth runtime 9). Full regression: **1955 passed**, 82 skipped. Changed-file Ruff PASS. `pip check` PASS. `git diff --check` PASS. CI after commit: all green.

Repo-wide `ruff format --check .` still contains pre-existing formatting findings unrelated to this correction. They were intentionally not mixed into the corrective slice.

### Corrective redeployment

- corrective image: `eci-api-dev:0050b30`
- final task definition: `eci-api-dev:6`
- semantic diff from revision 5: **IMAGE ONLY**
- ECS rollout: completed; final state 1 / 1 / 0; target HEALTHY
- connector GET after redeploy: **200**; former 503 resolved

Runtime log evidence: authentication → identity `find_existing` → `connector_accounts_listed` → `result_count=0`. No OAuth-store or provider operation occurred.

Local Docker/ECR login required an isolated Docker config because the host credential helper returned `The stub received bad data.` That is a local tooling workaround, not an AWS runtime or application defect.

### Zero-provider / safety proof

Phase 16D performed **zero**:

- Gmail API calls
- Microsoft Graph mailbox calls
- mailbox OAuth starts
- mailbox reauthorization
- mailbox message reads
- mailbox secret mutations caused by listing
- Bedrock inference
- Analyze operations
- Propose operations
- Approve operations
- Reject operations
- Send / Execute operations

AI output ≠ proposed action ≠ approved action ≠ sent action. No Send occurred.

### Security posture (validated)

- private S3 origin; CloudFront OAC; Block Public Access enabled
- HTTPS browser edge; separate SPA and API CloudFront distributions
- explicit CORS origin; no wildcard CORS
- Entra delegated scopes; OIDC API authorization
- `DATABASE_URL` via ECS secret reference; no plaintext DB URL in ECS environment
- no static AWS credentials; task role and execution role remain separate
- mailbox credential backend is durable AWS Secrets Manager; production memory store forbidden
- immutable ECR SHA tags; historical images retained
- no automatic live Send; no custom domain required

### Temporary IAM cleanup debt (Phase 16F)

Do **not** treat temporary operator policies as permanent runtime policy. Known temporary/operator policies created or used during 16D include items such as:

- `eci-phase16d-rds-create-temp`
- `eci-phase16d-rds-slr-temp`
- `eci-phase16d-rds-migration-secret-temp`
- `eci-phase16d-alb-foundation-temp`
- `eci-phase16d-spa-foundation-temp`
- `eci-phase16d-runtime-db-secret-temp`
- `eci-phase16d-spa-publish-temp`
- `eci-phase16d-stop-old-task-temp`

Known attachment facts: `eci-phase16d-stop-old-task-temp` was detached from `eci-developer` after Gate J because the managed-policy-per-user quota was reached. `eci-phase16d-spa-publish-temp` was subsequently attached for Gate K.

This closure does **not** claim current attachment or existence state for every other temporary policy.

Phase 16F must perform an explicitly authorized IAM inventory and remove temporary operator permissions that are no longer required.

Permanent runtime policies `eci-mailbox-secrets-runtime-dev` (task role) and `eci-runtime-db-secret-execution-dev` (execution role) are **not** 16D cleanup candidates merely because they contain Phase 16 runtime permissions.

### Planned cloud mutations

Consumed under explicit gates during 16D (S3, CloudFront SPA/API, ALB/TG, RDS, ECS image/task/service, Secrets Manager runtime IAM, Entra SPA redirect, CORS/OAuth return, Alembic against RDS). Gmail HTTPS callback registration and live mailbox OAuth were **not** exercised; they remain 16E.

### Authorization gates

Completed for hosting, Entra SPA redirect, browser MSAL, CORS, and protected reads. Live Gmail OAuth and live Bedrock inference were not authorized. Send/execute was not authorized.

### Cost gates

RDS is **material** and remains running for 16E. ALB is **standing hourly cost** while retained. CloudFront/S3 are usage. ECS is at desired/running 1 for the live 16D/16E environment; ALB still bills when compute is later scaled to zero. Sequential Azure/AWS database cost handling remains 16F.

### Live validation boundary

Browser MSAL against the CloudFront API. Protected analyses and connector-list reads. Live Gmail and Bedrock wait for 16E. No Send. Never send a real bearer token to task-IP HTTP.

### Expected tests

Offline focused and full frontend/backend regression. No live AWS/Gmail/Bedrock calls during 16D documentation closure.

### Offline regression (16D corrective commit)

- Focused backend (connector-list, lifecycle, dependency, OAuth runtime): **72 passed**
- Full backend `python -m pytest`: **1955 passed**, 82 skipped
- Changed-file Ruff: PASS
- `python -m pip check`: PASS
- `git diff --check`: PASS
- CI after commit: all green

Repo-wide `ruff format --check .` was not claimed. Pre-existing formatting findings remain outside this slice.

### Cost state after 16D

Retained: ECR storage, ECS Fargate desiredCount=1, ALB standing hourly, RDS PostgreSQL **material**, CloudFront/S3 usage, Secrets Manager low/usage, CloudWatch Logs 1-day. Azure PostgreSQL Flexible Server also remains from 16B/16C; sequential stop/pause of one paid database belongs to 16F under a separate authorization gate. Do not stop ECS or delete ALB/RDS in this closure.

### Exit criteria

SPA and API HTTPS hostnames live without custom domain; ECS registered behind ALB with healthy target; RDS migrated to `13a0001`; Secrets Manager backend selected; CORS/`FRONTEND_OAUTH_RETURN_URL` set to the SPA CloudFront origin; Entra/MSAL browser login PASS; connector-list 503 resolved; zero Gmail / Graph mailbox / Bedrock / Send. Working tree left unstaged/uncommitted.

---

## 16E — AWS Live Mailbox → Amazon Bedrock Validation

**Status: Next (not started).**

### Objective

Prove Gmail mailbox → Bedrock analyze → propose → approve on AWS. Stop before Send. 16D completed AWS HTTPS hosting only; 16E separately proves the real AWS mailbox/AI path. Gmail credentials and Bedrock inference were **not** exercised in 16D.

### Planned cloud mutations

None required for the frozen hosting topology (16D is complete). Optional: one Bedrock invoke. Desired count may be raised then returned to 0.

### Authorization gates

Live Gmail OAuth; live Bedrock inference. Each separate. 16E has **not** started.

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

Reconcile documentation, confirm parity of the two proofs, apply cost hardening (stop databases, scale compute to zero, optionally delete ALB), and perform an explicitly authorized IAM inventory to remove temporary operator permissions that are no longer required.

### Planned cloud mutations

Stop/start or delete only under explicit gates. Never delete `rg-eci-dev`. Do not delete Key Vault/Foundry/ACR/ECS cluster as part of “cleanup” unless a later prompt explicitly says so.

### Authorization gates

Any stop, delete, ingress tighten-back, or IAM inventory/removal of temporary operator policies. Do not confuse temporary 16D operator policies with permanent runtime policies (`eci-mailbox-secrets-runtime-dev`, `eci-runtime-db-secret-execution-dev`).

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

ACA env **names** present in 16A: `AI_PROVIDER`, `APP_ENV`, `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT`, `AZURE_CLIENT_ID`, `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`, `OIDC_REQUIRED_PERMISSION`.

Missing in 16A: `DATABASE_URL`, `CREDENTIAL_STORE_BACKEND`, `AZURE_KEY_VAULT_URL`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_OAUTH_RETURN_URL`, Gmail OAuth, Microsoft mailbox OAuth.

### After 16B (Azure)

| Resource | 16B state |
|---|---|
| ACR `eciacrdev6c` | Added immutable tag `7518360`; historical tags retained |
| UAMI `eci-ca-identity-dev` | AcrPull + Foundry User + **Key Vault Secrets Officer** |
| `eci-github-deploy-dev` | Also Website Contributor on SWA `eci-web-dev` |
| ACA `eci-api-dev` | Image `eci-api:7518360`; revision `eci-api-dev--0000004`; public HTTPS; `allowInsecure=false`; min 0 / max 1 |
| SWA `eci-web-dev` | Free; West US 2; `https://witty-island-03f5de51e.7.azurestaticapps.net` |
| PostgreSQL `eci-pg-dev-susanta` | PG 16; `Standard_B1ms`; 32 GiB; HA off; TLS on; schema head `13a0001` |
| Entra `eci-web-dev` | localhost + SWA HTTPS SPA redirects |
| Mailbox OAuth apps | ACA HTTPS callbacks registered; unused in 16B |

ACA production Settings names now include the 16A set plus `DATABASE_URL` (secretref), `CREDENTIAL_STORE_BACKEND`, `AZURE_KEY_VAULT_URL`, `CORS_ALLOWED_ORIGINS`, `FRONTEND_OAUTH_RETURN_URL`, and Gmail/Microsoft OAuth (secrets via secretref).

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

### After 16D (AWS)

| Resource | 16D state |
|---|---|
| ECR `eci-api-dev` | Added immutable tag `0050b30` (digest `sha256:d2e8f50738729033ca58a390ca490a95c7a51f9944316e600eecfb14d3c46316`); historical tags retained |
| Service `eci-api-dev` | desiredCount 1 / running 1 / pending 0; PRIMARY COMPLETED; load balancer attached |
| Task def | `eci-api-dev:6`; image `0050b30`; semantic diff from revision 5 IMAGE ONLY |
| Target group | `eci-api-tg-dev`; exactly one HEALTHY target |
| ALB | `eci-alb-dev`; HTTP :80 origin; CloudFront is public HTTPS |
| API CloudFront | `E2IF9K4FM4A6WJ`; `https://dnookm0ucbhv1.cloudfront.net` |
| SPA CloudFront | `E1XFNK98P7PU2W`; `https://d1ut7j94w7lt3b.cloudfront.net` |
| S3 | `eci-web-aws-dev-034456343525`; private; Block Public Access all four enabled; website hosting not configured; OAC `eci-spa-oac-dev` |
| RDS `eci-pg-dev` | PostgreSQL 16.15; database `eci`; runtime role `eci_app`; Alembic `13a0001` |
| Execution role | `AmazonECSTaskExecutionRolePolicy` plus `eci-runtime-db-secret-execution-dev` |
| Task role | existing Bedrock invoke plus `eci-mailbox-secrets-runtime-dev` (no `ListSecrets`) |
| Credential store | `CREDENTIAL_STORE_BACKEND=aws_secrets_manager`; mailbox OAuth not exercised |
| Entra `eci-web-dev` | localhost + Azure SWA + AWS SPA CloudFront HTTPS redirects |
| Bedrock profile | ACTIVE; **not invoked** |
| Gmail / Graph mailbox | **not configured and not exercised** |

`DATABASE_URL` is an ECS secret reference (plaintext absent from task environment). CORS and `FRONTEND_OAUTH_RETURN_URL` are the SPA CloudFront origin. Gmail/Microsoft mailbox OAuth provider settings were not required for 16D listing.

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
| `GMAIL_OAUTH_REDIRECT_URI` | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io/api/v1/oauth/callbacks/gmail` | runtime URL |
| `MICROSOFT_OAUTH_CLIENT_ID` | existing Graph mailbox app | public identifier |
| `MICROSOFT_OAUTH_CLIENT_SECRET` | secret reference — never in Git | secret |
| `MICROSOFT_OAUTH_REDIRECT_URI` | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io/api/v1/oauth/callbacks/microsoft_graph` | runtime URL |
| `MICROSOFT_OAUTH_TENANT` | existing tenant alias or GUID | public identifier |
| `CORS_ALLOWED_ORIGINS` | `https://witty-island-03f5de51e.7.azurestaticapps.net` | runtime URL |
| `FRONTEND_OAUTH_RETURN_URL` | `https://witty-island-03f5de51e.7.azurestaticapps.net` (fixed; never from query) | runtime URL |

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
| `DATABASE_URL` | ECS secret reference to RDS `eci-pg-dev` (plaintext absent from task environment) | secret + runtime URL |
| `AI_PROVIDER` | `amazon_bedrock` | public identifier |
| `BEDROCK_REGION` | `eu-south-2` | public identifier |
| `BEDROCK_MODEL_ID` | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` | public identifier |
| `CREDENTIAL_STORE_BACKEND` | `aws_secrets_manager` | public identifier |
| `AWS_SECRETS_MANAGER_REGION` | `eu-south-2` | public identifier |
| `AWS_SECRETS_MANAGER_NAMESPACE` | `eci/mailbox-oauth` (default) | public identifier |
| Gmail OAuth trio | same client as local; intended callback on API CloudFront HTTPS; **not configured or exercised in 16D** | identifier + secret + runtime URL |
| Microsoft OAuth quartet | live matrix does not require Graph on AWS; **not configured or exercised in 16D** | identifier + secret + runtime URL |
| `CORS_ALLOWED_ORIGINS` | `https://d1ut7j94w7lt3b.cloudfront.net` | runtime URL |
| `FRONTEND_OAUTH_RETURN_URL` | `https://d1ut7j94w7lt3b.cloudfront.net` | runtime URL |

---

## Frontend build matrices

Same variable names. Same five full scope identifiers against `eci-api-auth-dev`. Different API base and redirect origin.

| Variable | Azure build | AWS build |
|---|---|---|
| `VITE_ECI_API_BASE_URL` | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io` | `https://dnookm0ucbhv1.cloudfront.net` |
| `VITE_ENTRA_TENANT_ID` | same tenant | same tenant |
| `VITE_ENTRA_SPA_CLIENT_ID` | `eci-web-dev` | `eci-web-dev` |
| `VITE_ENTRA_REDIRECT_URI` | `https://witty-island-03f5de51e.7.azurestaticapps.net` | `https://d1ut7j94w7lt3b.cloudfront.net` |
| `VITE_ECI_API_SCOPES` | `api://<eci-api-client-id>/communications:read,analyze,connect,workflow,send` (full identifiers) | same identifiers |

---

## Redirect / CORS matrix

| Row | LOCAL | AZURE | AWS |
|---|---|---|---|
| MSAL SPA redirect | `http://localhost:5173` | `https://witty-island-03f5de51e.7.azurestaticapps.net` | `https://d1ut7j94w7lt3b.cloudfront.net` |
| Gmail provider callback | `http://localhost:8000/api/v1/oauth/callbacks/gmail` | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io/api/v1/oauth/callbacks/gmail` | intended `https://dnookm0ucbhv1.cloudfront.net/api/v1/oauth/callbacks/gmail` (not configured or exercised in 16D) |
| Microsoft mailbox callback | `http://localhost:8000/api/v1/oauth/callbacks/microsoft_graph` | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io/api/v1/oauth/callbacks/microsoft_graph` | not required on AWS live matrix; not configured or exercised in 16D |
| `FRONTEND_OAUTH_RETURN_URL` | `http://localhost:5173` | `https://witty-island-03f5de51e.7.azurestaticapps.net` | `https://d1ut7j94w7lt3b.cloudfront.net` |
| CORS origin (that cloud’s API) | `http://localhost:5173` | SWA origin only | `https://d1ut7j94w7lt3b.cloudfront.net` (exact; no wildcard) |

CORS remains an explicit allowlist, no wildcard, `allow_credentials=false`. Each cloud API should allow **its matching SPA origin** plus localhost if local development is retained — not every deployed SPA origin.

---

## Ingress

### Azure (current → 16B)

16A: external HTTPS, `allowInsecure=false`, operator `/32`. That blocked browsers and Google/Microsoft OAuth redirects.

16B: public ACA HTTPS. Application OIDC is the primary access control. `allowInsecure=false`.

### AWS (16A → 16D)

16A: no ALB on the service; Fargate public IP; SG TCP 8000 operator `/32`; HTTP only. Unsafe for real bearer tokens (ADR-010).

16D: CloudFront HTTPS (`E2IF9K4FM4A6WJ`) → ALB HTTP (`eci-alb-dev`) → ECS :8000. Fargate SG allows ALB. ALB SG allows CloudFront prefix list. CloudFront is the public HTTPS API boundary. Task-IP HTTP remains verification-only if it still exists. Never send a real bearer token to task-IP HTTP.

---

## IAM / RBAC gap matrix

| Identity | Need | Current | Gap |
|---|---|---|---|
| Azure UAMI | AcrPull | Present | None |
| Azure UAMI | Foundry User | Present | None |
| Azure UAMI | Key Vault secrets data plane | **Key Vault Secrets Officer** (16B) | None — Secrets User cannot set/delete |
| Azure GitHub deploy UAMI | SWA deploy | Website Contributor on `eci-web-dev` (16B) | None for Azure SPA CD |
| AWS execution role | ECR pull + awslogs + `DATABASE_URL` secret reference | `AmazonECSTaskExecutionRolePolicy` plus `eci-runtime-db-secret-execution-dev` (16D) | None for 16D runtime |
| AWS task role | `bedrock:InvokeModel` on Haiku EU profile | Present | None (Bedrock **not invoked** in 16D) |
| AWS task role | Secrets Manager on `eci/mailbox-oauth/*`: CreateSecret, GetSecretValue, PutSecretValue, UpdateSecretVersionStage, DescribeSecret, DeleteSecret | **`eci-mailbox-secrets-runtime-dev` (16D)** | None — do **not** add `ListSecrets`; add KMS only if the namespace is CMK-encrypted |
| AWS GitHub deploy role | Existing ECR/ECS deploy | Documented; not inspectable by `eci-developer` | Extra S3/CloudFront deploy perms only if CD should upload the SPA |

---

## AI live-call cost gate

| Slice | Provider | Policy |
|---|---|---|
| 16C | Microsoft Foundry | Consumed: one selected-message analysis. No retry. No additional inference during 16C closure. |
| 16E | Amazon Bedrock | One selected-message analysis unless one explicit retry after failure |

Do not call either in 16A.

---

## PostgreSQL strategy

- Version: **PostgreSQL 16** (CI image `postgres:16`).
- Azure: Flexible Server in Spain Central, TLS required, firewall/VNet so ACA can connect.
- AWS: RDS PostgreSQL in the ECS VPC, TLS required, SG from `eci-fargate-sg-dev`.
- Credentials: injected `DATABASE_URL`; do not commit passwords. Entra/IAM DB auth remains future (ADR-014).
- Migration: `alembic upgrade head` once per new database. Current head: **`13a0001`**. No new revision in 16A, 16B, 16C, or 16D.
- Advisory locks: required for durable credential mutations (`pg_advisory_xact_lock`).
- Sequential: Azure proof first, then stop/pause Azure PG before RDS (or reverse) so both are not standing indefinitely.

Database cost gates: Azure Flexible Server exists after 16B; RDS `eci-pg-dev` exists after 16D. Sequential validation still applies so both paid databases are not left standing indefinitely (16F). Stop may still bill storage; delete destroys data.

---

## CI/CD plan

Current: `.github/workflows/ci.yml` (automatic tests, including frontend); `.github/workflows/deploy.yml` (`workflow_dispatch` azure/aws/both; optional `azure_frontend`; backend image plus Azure SPA).

Phase 16B implemented:

- Keep **manual** `workflow_dispatch`. Do not auto-deploy on push.
- Backend Azure job still builds once, pushes SHA (+ `stable` on CD), updates ACA image only. ACA secrets/env and `alembic upgrade head` remain operator steps.
- Frontend Azure job: production Vite build from GitHub environment `azure` public `VITE_*` variables, then SWA deploy via Azure OIDC. Use `SWA_CLI_DEPLOYMENT_TOKEN` (never pass the token as a CLI flag). Required GitHub environment variables: `AZURE_STATIC_WEB_APP_NAME`, `VITE_ECI_API_BASE_URL`, `VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_SPA_CLIENT_ID`, `VITE_ENTRA_REDIRECT_URI`, `VITE_ECI_API_SCOPES`. GitHub deploy UAMI has Website Contributor on `eci-web-dev`.

---

## IaC decision

**No.** Phase 16 does not introduce Terraform, Bicep, CDK, or CloudFormation.

---

## Mailbox OAuth client reuse

Reuse existing development Google and Microsoft mailbox OAuth apps. Phase 16B added ACA HTTPS redirect URIs and kept local HTTP callbacks. Do not create new OAuth applications unless a provider refuses additional URIs. 16B did not start mailbox OAuth.

---

## Application-code review (16A)

- Backend: **no change required for hosting.** Gaps were configuration, RBAC, ingress, and hosting.
- Frontend: **no change required.** Per-environment Vite builds are sufficient. Runtime config JSON and cloud selectors are out of scope.
- Alembic: **no new revision.** Head remains `13a0001`.

Phase 16D later corrected a composition defect: `GET /api/v1/connector-accounts` now uses `get_connector_account_listing_service` (`communications:read`, persistence only) instead of the connect/lifecycle factory. That is not a new architecture decision. Disconnect/reauthorize remain `communications:connect` with credential-store requirements intact.

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

Hosting gates 1–8 were consumed in 16D (S3, CloudFront SPA/API, ALB, RDS, ECS, Secrets Manager runtime IAM, security groups, Entra SPA redirect). Remaining:

9. Gmail callback addition (if not already registered; not exercised in 16D)
10. Microsoft callback addition if needed (not required for the AWS live matrix)
11. Live Gmail OAuth (16E)
12. Live Bedrock inference (16E)

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
