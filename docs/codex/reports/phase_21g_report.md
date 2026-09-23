# Phase 21G — Cloud deployment and live validation

> **Current closure — 2026-09-23: Phase 21G PASS; Phase 21 CLOSED for the
> delivered XLSX scope.** Both clouds completed manual deployment and functional
> validation, as reported by the operator. Sections 1–63 below are preserved
> historical checkpoints, including the failed Azure frontend upload; their
> BLOCKED/OPEN verdicts and pending actions are superseded by sections 64–67.
> Closure does not certify every security case live or authorize Phase 22.

## 1. Executive summary

PHASE 21G RESULT: BLOCKED

PHASE 21 RESULT: OPEN

2026-09-21 frontend checkpoint: the separately approved single Azure frontend
upload failed with deployment-client exit 1 because its working directory was
inside the artifact directory. Public site still serves the verified Phase 20
HTML/JS. SWA production/default now reports Uploading, not Ready, on two
post-failure status reads; no retry performed. See section 63. Phase 21 frontend
deployment and native XLSX Analyze remain incomplete.

2026-09-20 Azure backend deployment checkpoint: individually approved backend
deployment completed; revision `eci-api-dev--p21g-63669ec-20260920` is Healthy,
active and ready, with production health/readiness HTTP 200. Earlier Azure
`21d0001` migration and ACR push remain complete. No frontend upload, AWS mutation,
mailbox retrieval or live AI invocation occurred. The interim BLOCKED verdict
means overall acceptance remains outstanding pending separately approved frontend,
AWS migration/deployment and live validation; it is not a backend rollout failure.

## 2. User authorization scope

Existing Azure/AWS development environments only; migration `21d0001` where
required. Each consequential command needs individual approval. No new
infrastructure, destructive operation, IAM expansion, Git commit/push, Send, or
Phase 22 work. No persistent command approvals were requested. Read-only commands
requiring host/network access used explicit sandbox escalation. User subsequently
approved exactly one push of `eci-api:63669ec-p21g-20260920` to existing ACR after
local validation. User separately approved exactly
`python .phase21g-artifacts/azure_migration.py --apply`; that command was executed
once successfully. User then separately approved the exact Azure Container App
update in section 8; executed once successfully. All three individual approvals
have been used; no additional cloud mutation is approved.

## 3. Local baseline

- Branch: `master`; HEAD: `63669ec8bdf27158817e4fe56858fd3df3ce3086`.
- Existing tracked modifications and untracked Phase 21A–F implementation,
  migration, tests, reports, AGENTS.md and validation artifacts preserved.
- `alembic heads`: exactly one head, `21d0001`; parent `20c0001`.
- Required reports, roadmap, README, AGENTS.md, cloud runbooks, Dockerfile,
  Docker ignore/Compose configuration, deployment/CI workflows and persistence
  migration guidance inspected.
- Docker client/server: `29.5.2` / `29.8.0`; daemon accessible after escalation.
- Azure CLI: `2.89.1`; AWS CLI: `2.36.24`.
- `git diff --check`: PASS before report creation; checked again afterward.
- At discovery, no tests were rerun. Artifact-stage focused tests are below. Accepted Phase 21F
  evidence remains historical: 2,681 backend (including 94 PostgreSQL), 369
  frontend tests across 30 files, 15 offline provider parity cases.

## 4. Azure identity/resource discovery

Active signed-in user identity verified; identity type `user`. Subscription is
`ECI-Development`, Enabled and default. Subscription/tenant identifiers inspected
but omitted here per repository privacy guidance. No subscription switch.

Existing deployment group `rg-eci-deploy-dev` is Succeeded in Spain Central.
Inventory contains ACR `eciacrdev6c`, identities `eci-ca-identity-dev` and
`eci-github-deploy-dev`, environment `eci-ca-env-dev`, app `eci-api-dev`, Log
Analytics `eci-law-dev`, Key Vault `eci-kv-oauth-dev-susanta`, SWA `eci-web-dev`,
and PostgreSQL `eci-pg-dev-susanta`. SWA is in West US 2.

`rg-eci-dev` contains Foundry `eci-foundry-dev-susanta`, project
`eci-project-dev`, and External ID directory `eciexternaliddev`.

Backend: `eci-api-dev--0000011`, image
`eciacrdev6c.azurecr.io/eci-api:ed5eebc-p20g`. Provisioning Succeeded; active
revision Healthy / ScaledToZero, zero replicas; min/max 0/1. HTTPS ingress,
port 8000, latest revision receives 100% traffic. API has 0.5 CPU / 1 GiB;
existing ClamAV sidecar has 1 CPU / 2 GiB, image
`eciacrdev6c.azurecr.io/eci-clamav:1.4-b25d9199257a`.

Frontend: existing `eci-web-dev`, Free SKU, hostname
`witty-island-03f5de51e.7.azurestaticapps.net`.

Database: existing PostgreSQL 16 server `eci-pg-dev-susanta`, Ready,
Standard_B1ms, database `eci`. Read-only transaction verified current database,
revision `20c0001`, two attachment-analysis rows, absent `tabular_result`, and
kind constraint allowing pdf/docx/jpeg/png/txt only. Credential retrieved into
process memory from existing ACA secret; not printed or saved. Initial attempt
without CLI `--show-values` returned no value; corrected read succeeded.

ACR is Succeeded, admin authentication disabled. Established deployment mechanism
is local shared image build/push, app-image-only update preserving sidecar and
configuration, cloud-specific frontend build and SWA deployment. GitHub dispatch
would omit this uncommitted implementation and was not triggered.

Allowlisted runtime settings verified: production, OIDC, microsoft_foundry,
azure_key_vault, clamav at localhost:3310. Foundry project reference matches
existing project; model deployment `eci-gpt-54-mini` is Succeeded, model
`gpt-5.4-mini`, version `2026-03-17`. Configuration readiness is not live
inference proof.

## 5. AWS identity/resource discovery

Earlier default-profile authentication failure is resolved for this work by the
user's explicit confirmation to use `--profile eci-dev --region eu-south-2`.
Default CLI configuration was not changed. Resumed AWS read-only calls succeeded
after network sandbox escalation; no login or IAM change was performed.

User manually verified caller `eci-developer` and the intended development account
(full account ID omitted here per repository guidance), actual cluster
`eci-cluster-dev`, service `eci-api-dev` ACTIVE at desired/running/pending 1/1/0,
task definition `eci-api-dev:12`, image tag `ed5eebc-p20g`, and RDS `eci-pg-dev`
available with database `eci` at Alembic `20c0001`. These service/DB facts are
operator-attested, not a fresh agent SQL or service query. The earlier cluster
reference `eci-dev` is stale; that string is the CLI profile, not the ECS cluster.

Agent read-only verification on resume:

- Task definition `eci-api-dev:12` ACTIVE; Linux/X86_64; ECR image matches the
  user-confirmed account, repository `eci-api-dev`, tag `ed5eebc-p20g`.
- Task CPU 1024 / memory 3072 MiB. API `eci-api` memory reservation 512 MiB;
  ClamAV reservation 2048 MiB. Neither has a separate hard container memory limit.
  This is not a verified 1 GiB API limit. Preserve actual settings during rollout.
- Existing `clamav/clamav:1.4` sidecar; scanner localhost:3310; healthchecks and
  `/ecs/eci-api-dev` logging on both containers. DATABASE_URL and Gmail client
  secret are secret references; no secret values read.
- Production/OIDC, aws_secrets_manager, amazon_bedrock, eu-south-2 configured.
- Bedrock profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0` ACTIVE,
  SYSTEM_DEFINED. No inference performed; runtime access still needs live proof.
- ECR `eci-api-dev` exists in the confirmed account/region, mutable tags,
  scan-on-push enabled.
- SPA CloudFront `E1XFNK98P7PU2W` enabled/Deployed at
  `d1ut7j94w7lt3b.cloudfront.net`, pointing to the existing ECI private-origin
  bucket reference. API CloudFront `E2IF9K4FM4A6WJ` enabled/Deployed at
  `dnookm0ucbhv1.cloudfront.net`, pointing to `eci-alb-dev`.

Deployment mechanism: shared Linux/amd64 image to existing ECR; register an
image-only revision based on the service's current task definition, preserving
scanner/settings; update existing ECS service. Build frontend in AWS mode, upload
to existing S3 origin and invalidate existing SPA distribution. Each consequential
command requires its own approval. No resource replacement.

Mandatory checkpoint was presented and the user approved this single first cloud
mutation after validation. Executed successfully:

```sh
docker push eciacrdev6c.azurecr.io/eci-api:63669ec-p21g-20260920
```

Read-only ACR tag query returned an empty list both before approval and immediately
before push. Subscription and local image ID were asserted before execution.
ACR authentication used an automatically removed temporary Docker configuration
inside the repository; no token printed or retained in report/artifacts. HEAD in
the tag identifies the baseline, not a committed Phase 21 release: the image
contains preserved uncommitted Phase 21 implementation. Approval covered this one
push only, not migration, deployment, frontend upload, or AWS actions.

## 6. Artifact/build details

Shared backend built from existing Dockerfile with `--platform linux/amd64`.
Final image/tag: `eciacrdev6c.azurecr.io/eci-api:63669ec-p21g-20260920`.

- Local image ID / pushed OCI index / independently read ACR digest:
  `sha256:718933ccde31a4d8caf88079e50312c3d13204b604e915d5818abba34d4bf9cb`.
- Linux/amd64 platform manifest:
  `sha256:f94645754f49be1de3d83f2608639e51392ce449f988802cc7ff01eceffa5349`.
- Image size reported by Docker: 541,032,873 bytes; user `appuser`, UID 1000.
- Base `python:3.12-slim` resolved to
  `sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9`.
- Registry verification timestamp: `2026-09-20T08:25:55.8701632Z`.
- `openpyxl 3.1.5` present. Image `pip check` PASS. Existing minimum-version
  dependency policy unchanged; build resolves current packages (including
  openai 3.16.2, azure-ai-projects 2.7.0, boto3 1.43.98). Live compatibility
  remains a subsequent provider gate; no dependency pinning changes made.

Initial packaging audit found nested `__pycache__` files including an orphaned
compiled module. Added recursive `**/__pycache__` and `**/*.py[cod]` exclusions
to `.dockerignore`, then rebuilt. Initial candidate was not pushed. Final image
inventory matches SHA-256 hashes of all 203 application files, with no nested
caches or extra application files. Image configuration/history has no supplied
cloud credential; packaged /app inventory has no env/credential/key/test/frontend
files. No pandas, pytest or browser automation package installed in release image.
This is packaging inspection, not an exhaustive third-party secret/CVE audit.

Validation:

- Host focused XLSX policy/hardening/parser/provider parity: **86 passed in 3.66s**.
- Host ruff, pip check and git diff --check: PASS.
- Rebuilt image network-isolated smoke under a 1 GiB limit: PASS, non-root,
  synthetic XLSX parse, inert formula, bounded row truncation, validated Mock
  tabular result, Foundry/Bedrock adapter imports and dependency consistency.
- Image TestClient startup, `/health`, `/api/v1/health`, `/api/v1/readiness`: 200.
  This used development configuration without database or scanner; it is not
  production DB readiness, actual clamd clearance, Uvicorn probe, or cloud proof.
- No backend source change, new migration, full-suite rerun or cloud AI invocation.

Both cloud-specific frontend builds PASS (334 modules each), saved separately
outside frontend source scanning under `.phase21g-artifacts/frontend-azure/` and
`.phase21g-artifacts/frontend-aws/`. Existing output directories preserved. One
intermediate npm invocation from repository root failed to locate package.json;
corrected commands ran from frontend/. Existing non-blocking >500 kB bundle
warning remains. Public API target isolation checked in each bundle; selected
private-key/DB-URL/client-secret markers absent. No frontend deployed.

Azure JS `index-BQKDgcbq.js`, SHA-256
`00dc87b6ecc7f1534e05e1803cafb849cd4d562b6ff62c0da20e0ff72064c1c0`.
AWS JS `index-BsxIj7rg.js`, SHA-256
`87e81cff03334f2f28c376aec4740e76769ccd00719140277ef2c395505c6658`.
12 generated frontend files are recorded in
`.phase21g-artifacts/frontend-sha256.json`.

Image does not package Alembic migrations; migration remains an operator step.

## 7. Azure DB migration

**PASS — applied and verified `21d0001`.** Approved wrapper rechecked subscription,
target database and expected `20c0001` predecessor immediately before invoking
the existing migration. Command exited 0; post-migration read-only verification
confirmed nullable PostgreSQL JSONB `tabular_result`, the XLSX kind constraint,
and two total attachment-analysis rows. Both pre-existing rows retained identical
legacy-field fingerprints. No new table, downgrade, manual DDL or artificial
XLSX row inserted. Existing serving image is still Phase 20.

Migration preparation: `.phase21g-artifacts/azure_migration.py` is a
wrapper around the existing operator Alembic procedure. Default mode is read-only.
Refreshed preflight PASS: exact subscription identity, TLS-protected server
`eci-pg-dev-susanta.postgres.database.azure.com`, database `eci`, revision
`20c0001`, expected kind constraint, absent tabular column, two existing rows.
Migration SHA-256 locked to
`22c803b22c580097b042b37a767554f6353e9b7ad8d097686eee9cb942d63ba8`;
single local head and predecessor checked. No build, validation suite or push
repeated. Initial helper preflight hit a local SQLAlchemy result conversion
TypeError; corrected handling, then read-only preflight and helper ruff passed.
No migration was attempted by either preflight invocation.

Exact individually approved command, **executed once successfully**:

```sh
python .phase21g-artifacts/azure_migration.py --apply
```

The wrapper repeats target/source guards, holds credentials in memory, invokes
`python -m alembic upgrade 21d0001` with the existing repository configuration,
then verifies target revision, nullable JSONB, XLSX kind constraint and preservation
of every pre-existing attachment row using in-memory legacy-row fingerprints.
Only counts and sanitized metadata are printed. DB connection timeout is 10 seconds,
DDL lock timeout 10 seconds and statement timeout 60 seconds. No automatic retry
or downgrade. A failed postcondition requires inspection of actual state.

Compatibility: migration adds a nullable column and broadens an existing kind
constraint; existing Phase 20 application can continue using legacy columns/kinds.
Phase 21 backend rollout must follow successful migration, under separate approval.
The used approval covered Azure database migration only, not deployment or AWS.
Do not rerun apply: the database is now at target and the predecessor guard will
refuse. No new test-suite/build/push run was needed for this execution. Report
whitespace validation passed after the checkpoint update.

## 8. Azure deployment

**PASS — approved backend rollout and deployment health checks.** New revision
`eci-api-dev--p21g-63669ec-20260920` is latest and latest-ready, active, Provisioned,
Healthy and RunningAtMaxScale with one replica. Full live XLSX acceptance remains
separate. No frontend deployment occurred.

Deployment approval preparation (historical read-only baseline): latest/ready revision was
`eci-api-dev--0000011`, Healthy/ScaledToZero. Verified Single revision mode with
100% traffic to latest, API container name `eci-api-dev`, API 0.5 CPU/1 GiB,
ClamAV 1 CPU/2 GiB, and min/max replicas 0/1. Proposed suffix below is absent
from the revision list. CLI confirms container-name and revision-suffix options.

Exact individually approved Azure deployment command, **executed once successfully**:

```sh
az containerapp update \
  --subscription ECI-Development \
  --resource-group rg-eci-deploy-dev \
  --name eci-api-dev \
  --container-name eci-api-dev \
  --image eciacrdev6c.azurecr.io/eci-api@sha256:718933ccde31a4d8caf88079e50312c3d13204b604e915d5818abba34d4bf9cb \
  --revision-suffix p21g-63669ec-20260920 \
  --query '{revision:properties.latestRevisionName,ready:properties.latestReadyRevisionName,state:properties.provisioningState}' \
  --output json
```

Verified revision: `eci-api-dev--p21g-63669ec-20260920`, using the immutable digest
already verified for tag `63669ec-p21g-20260920`. This updates only the API image
and revision suffix in the existing Container App. Existing scanner image,
resources, scale, identities, environment and secret references are preserved.
Compared full old/new revision templates in memory: identical after excluding
only API image and revision suffix. Scanner image/resources, API limits, scale,
environment and secret references therefore match the prior template. Identity
configuration was not changed by the command. Single-revision mode retains 100%
traffic to latest; final revision list shows only the new revision active/healthy.
Both containers are Running/ready with zero restarts. Minimum replicas stays zero;
no manual scaling, traffic change, infrastructure creation or restart command.

Update initially returned Succeeded with the old latest-ready revision; subsequent
read-only checks verified the new revision became latest-ready. Endpoint evidence:

- Initial `/health` request timed out after its 30-second timeout; cause was not
  independently established. Retry after readiness succeeded: 200, healthy, 0.12 s.
- `/api/v1/health`: 200, healthy, production, scanner configured, image AI
  unavailable, 24.88 s during initial rollout checks.
- `/api/v1/readiness`: 200, ready, 0.24 s (configured DB connectivity probe).

Read-only console diagnostics: 13 API log records and 68 scanner records inspected
in memory. API application_startup and Uvicorn-running markers present; zero
error-keyword lines, traceback markers or OOM markers in both bounded samples.
No raw log lines printed/saved. Scanner container readiness is established, but
this is not an actual CLEAN attachment-scan proof. No Analyze/AI/mailbox call.

## 9. Azure live XLSX validation

Not performed: metadata listing, explicit Analyze, provenance, CLEAN scanner,
bounded extraction, formula non-execution and valid structured result remain gates.

Live-validation preparation only: inspected prior Phase 18/20 test path, application
auth/read handlers and refresh lifecycle. A read-only Azure DB transaction found
three ACTIVE Microsoft Graph connector records with the same display mailbox,
owned by three different application users (two ordinary users, one owner).
One ordinary user's connector owns both historical attachment analyses. The initial
ordinary-user proposal is superseded by the operator's corrected identification
of the existing Platform Owner login and its own connected Outlook mailbox.
Do not transfer or use the ordinary user's historical records as this owner's data.
No mailbox credential fetched, provider mailbox request, attachment
retrieval, token acquisition or authenticated application request performed.
Display email is not an authorization key; no selection based on matching email
alone. Account display address was shown to the operator, omitted from this report.

The application login name cannot be determined from DB records: users have no
PII columns and external identities contain issuer/subject mappings. The operator
subsequently identified the existing Platform Owner application login and separately
identified its Outlook mailbox; the two display addresses happen to match. The
earlier alternative login identification is superseded. An authenticated
owned-connector listing can then verify the exact owned record, without exposing
internal user IDs in this report. Do not substitute the cloud CLI identity or use
the Platform Owner connector to bypass ownership.

Proposed route: direct authenticated API validation through the existing Azure
SPA/MSAL session, operator-assisted because this session has no browser tool or
established ECI bearer-token access. Current deployed SPA is still Phase 20;
it cannot prove Phase 21 XLSX Analyze UI/rendering. No frontend upload proposed
under the present live-validation-only scope; UI gates remain outstanding.

First authenticated request (operator-observed browser evidence, PASS):

```http
GET /api/v1/me
Host: eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io
Authorization: Bearer <existing ECI application access token, never shared in chat>
```

Operator now confirms the existing Azure frontend session is authenticated, with
Platform Owner role, Azure environment badge and the existing Outlook connection
displayed as Active / mailbox available. This is operator-observed UI evidence,
not an agent-verified /me HTTP response or proof of mailbox token validity. Operator
authorizes the read-only /me validation only; no fresh login/token renewal, mailbox
refresh, Analyze or application-data mutation. No actual browser-control tool or
access to that browser's ECI bearer token is available in this agent session.
Operator inspected the existing Azure browser /me request and supplied HTTP 200
with exactly `{"application_role":"owner","is_owner":true}`. No login, token
renewal, mailbox refresh, Analyze or application-data mutation performed during
this validation. Evidence is operator-observed, not an agent-issued request.
Do not reload the SPA or invoke MSAL acquireTokenSilent while token renewal remains
unapproved.

Next step: inspect the existing signed-in browser's owned-connector response
`GET /api/v1/connector-accounts` to bind the selected ACTIVE Microsoft Graph
connection to this authenticated user, rather than selecting one of three DB
records by display email. This endpoint reads existing owned records without
provider mailbox I/O, identity creation or mailbox credential refresh. No new
authenticated request issued by the agent. Operator-assisted network evidence
remains required; retain the connector ID privately in the browser. Following
that check, one bounded message-list request can be proposed for separate approval
because its credential lifecycle can write even though message listing is a GET.

The inspected /me handler verifies issuer/subject and reads existing identity/role;
it does not create users, touch mailbox credentials or persist business data.
Normal request/security telemetry can be persisted. If a valid existing session
is unavailable, login/token refresh can create identity-provider audit/session
records and browser session storage; obtain approval before that separate action.

Later mailbox metadata GETs can refresh credentials in Key Vault or mark an owned
connector reauth_required on permanent refresh failure, despite being GETs.
They require separate approval under the current no-data-mutation boundary.
Explicit XLSX Analyze would retrieve one attachment, require CLEAN scanning,
call Foundry and persist one validated attachment-analysis result on success;
it also needs its own approval after exact existing fixture provenance is known.
No fixture existence/validity is assumed from historical XLSX rejection evidence.

## 10. Azure Foundry validation

Existing configuration/model deployment verified; no live provider call.

## 11. Azure Outlook validation

Owned-connector metadata validation PASS via operator inspection of the existing
authenticated browser response: microsoft_graph, active, expected Outlook display
identity, mail.read granted. mail.send is also granted but remains strictly out
of scope. No login, token renewal, mailbox refresh, Analyze or application-data
mutation during this check. This confirms stored connection metadata, not a live
Graph request or current provider-token validity. No new mailbox connected.

Next proposed action, pending separate approval: exactly one bounded request,
using the owned connector ID already held in the existing browser:

```http
GET /api/v1/connector-accounts/{owned_connector_id}/messages?page_size=10
Host: eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io
```

Use the existing ECI access token directly; no application login/MSAL renewal.
This retrieves one page of recent message metadata to locate an existing safe
test message. It does not list attachment metadata, retrieve attachment bytes,
invoke AI, create analysis/workflow/business records, send or modify messages.
Normal logs persist. Mailbox credential resolution may refresh the existing
delegated token and persist replacement credentials in Key Vault; permanent
refresh failure may mark the owned connector reauth_required in PostgreSQL.
Approval must cover these lifecycle effects for this single request. No automatic
retry, pagination, reconnect or follow-up attachment/Analyze request is proposed.
If application token is expired or reauthentication is required, stop for approval.
No message-list request performed yet; operator-assisted execution is required
because the agent has no access to the authenticated browser/token.

## 12. Azure persistence/history

Migration schema and legacy-row preservation verified. XLSX persistence/history
through the deployed application remains untested.

## 13. Azure ownership/auth

OIDC runtime setting verified. Existing-session `/api/v1/me` PASS via operator
DevTools evidence: HTTP 200, application_role owner, is_owner true. Owned-connector
response validated by operator for this same session. No identity creation/role
mutation. Cross-user ownership-isolation proof remains outstanding; these checks
alone do not satisfy the full ownership gate.

## 14. Azure BusinessContext compatibility

Not live-tested; no BusinessContext mutation performed.

## 15. Azure logging/privacy

Bounded startup logs inspected as recorded in section 8; no observed error,
traceback or OOM markers. Raw logs stayed in memory. No live XLSX-content leakage
test yet; startup evidence does not satisfy that gate. Credentials not exposed.

## 16. Azure resource/performance observations

After rollout: one healthy replica, API 1 GiB plus separate 2 GiB scanner, both
containers ready with zero restarts. One initial health timeout then 200 on retry;
timings in section 8. No sampled OOM markers. No XLSX workload, CPU/memory usage
measurement or concurrency/capacity claim; resource gate remains incomplete.

## 17. AWS DB migration

Not attempted. User manually verified RDS `eci-pg-dev`, database `eci`, revision
`20c0001`; target `21d0001`. Agent schema/count baseline and immediate pre-migration
revision recheck remain required before migration approval/execution.

## 18. AWS deployment

Not attempted. Existing service ACTIVE at 1/1/0 is user-verified; task definition
and Phase 20 image/configuration verified by agent. Waiting at approval checkpoint.

## 19. AWS live XLSX validation

Not performed; all live functional/security gates remain unverified.

## 20. AWS Bedrock validation

Configuration and ACTIVE inference profile verified; live inference not performed.

## 21. AWS Gmail validation

Not performed; no mailbox connected or attachment retrieved.

## 22. AWS persistence/history

Not performed.

## 23. AWS ownership/auth

Not performed; application identity not accessed.

## 24. AWS BusinessContext compatibility

Not live-tested; no business-state mutation performed.

## 25. AWS logging/privacy

Deployment logs not inspected. No AWS credential, mailbox content or provider
response retrieved or stored.

## 26. AWS resource/performance observations

User verifies existing service 1/1/0. Agent verifies 1 vCPU / 3 GiB task including
API and ClamAV, reservations 512/2048 MiB respectively. No workload measurements,
OOM/restart review, or concurrency/capacity claim.

## 27. Browser/product validation

Not performed. No browser tool is exposed in this session; no browser automation
infrastructure installed. This does not prove that operator browser testing is
impossible. Login, mailbox, Analyze/loading/results and history revisit remain open.

## 28. Unsupported/malformed format validation

Not performed live on either cloud. Phase 21F local proof is not cloud acceptance.

## 29. Truncation validation

Not performed live; persisted flags and visible disclosure remain open.

## 30. Advisory-boundary validation

No Analyze/Send/workflow/business-state action performed. Deployed Phase 21
advisory-only behavior has not yet been exercised.

## 31. Final cloud resource state

Approved ACR push, Azure database migration and Azure backend rollout completed.
Azure database `eci` was verified at `21d0001`, two existing rows preserved.
Latest/ready revision is `eci-api-dev--p21g-63669ec-20260920`, using the approved
digest; scanner/template preserved. Health/readiness 200; one healthy running
replica, both containers ready, zero restarts; no pending failed revision observed.
AWS service 1/1/0 and available RDS are user-verified; configuration references
are agent-verified as recorded above. No start, stop, resize, delete, restart or scale operation.
Azure backend updated only as approved and left running. AWS serving configuration
untouched; full Phase 21 serving acceptance on both clouds remains outstanding.

Acceptance gates: Azure 1 (existing infrastructure discovery), 2 (migration),
and 3 (healthy deployment) PASS; Azure 4–19
not satisfied by this checkpoint. AWS 20 discovery established through combined
operator and agent evidence; AWS 21–38 remain outstanding. Global 39–42 PASS for
this work (no new infrastructure, migration beyond target, commit/push, Phase 22).
Global 43 not fully established: Azure backend healthy, but final both-cloud
Phase 21 serving state has not been verified. Overall closure is blocked.

## 32. Files created

- `docs/codex/reports/phase_21g_report.md`.
- Local artifacts: `.phase21g-artifacts/` (12 frontend output files and hash manifest).
- Migration checkpoint helper: `.phase21g-artifacts/azure_migration.py` (default read-only).

## 33. Files modified

Updated this Phase 21G report and `.dockerignore` (two recursive cache exclusions).
All prior implementation work retained. Roadmaps not updated to PASS.

## 34. Cloud resources modified

- Existing Azure ACR `eciacrdev6c`, repository `eci-api`: pushed tag
  `63669ec-p21g-20260920` with verified digest above (earlier approval).
- Existing Azure PostgreSQL server `eci-pg-dev-susanta`, database `eci`:
  applied only Alembic `20c0001 → 21d0001`, updating attachment schema and
  Alembic version; legacy rows preserved (earlier approval).
- Existing Azure Container App `eci-api-dev` in `rg-eci-deploy-dev`: approved
  API digest rollout to revision `eci-api-dev--p21g-63669ec-20260920` (current approval).

No frontend upload, AWS mutation or infrastructure creation.

## 35. New infrastructure confirmation

No new infrastructure created by this work in either cloud.

## 36. Remaining limitations

AWS profile/account ambiguity is resolved and authenticated read-only discovery
succeeded. Local release builds/validation, approved ACR push and approved Azure
migration/backend rollout completed. Further individual mutation approvals,
frontend upload, AWS migration/deployment, live E2E gates,
browser testing, log review and cloud resource observations remain outstanding.
Azure DB target `21d0001` is agent-verified; AWS source `20c0001` is user-attested.
Recheck database identity/revision and preserve pre-upgrade row/schema evidence
before each later migration. Do not close Phase 21 based on local Phase 21F
results or historical Phase 20 deployment evidence.

## 37. Phase 21 closure decision

PHASE 21G RESULT: BLOCKED

PHASE 21 RESULT: OPEN

## 38. Phase 22 readiness

Not cleared by this phase; do not start Phase 22. After Phase 21G is completed and
accepted, a fresh Codex session with its closure report is recommended for Phase 22.

## 39. Resumed mailbox-list approval checkpoint

On resume, repository HEAD remains `63669ec`; existing uncommitted Phase 21 work
is preserved. The roadmap's “not started” status is stale relative to the Azure
deployment evidence above and the operator's IN PROGRESS handoff. Overall Phase
21 remains OPEN; no acceptance gate is newly satisfied by this checkpoint.

The operator explicitly approved exactly one request:
`GET /api/v1/connector-accounts/{owned_connector_id}/messages?page_size=10`
against the Azure API, using the existing authenticated browser session and its
previously verified owned connector. Approval includes request-driven mailbox
credential refresh/persistence, permanent-refresh-failure reauthorization status,
and normal telemetry. It excludes automatic retries, pagination, attachment
retrieval, Analyze/AI, separate token renewal, and follow-up application mutations.

Available tools were inspected on resume: no authenticated-browser control tool
is exposed. Execution remains operator-assisted; no mailbox request was issued
by the agent, and no response or live mailbox success is claimed. Approval is
recorded, execution/result pending. No cloud action, build, deployment, migration,
or test suite was repeated at this checkpoint.

## 40. First Azure mailbox-list result (operator-observed)

The operator executed the approved mailbox-list request exactly once. CORS
preflight ultimately passed and the actual GET `/messages?page_size=10` returned
HTTP 200. DevTools did not retain/expose the response body; returned item count,
response contents and safe test-message identification remain unverified. No
retry was performed. This establishes operator-observed live listing HTTP
success, not XLSX fixture provenance or attachment/AI acceptance. The single
request approval is consumed; actual credential-lifecycle writes were not audited.

Next minimal proposed action: separately approve one more identical bounded GET,
explicitly consuming its JSON response in the browser and retaining it only in
page memory for private operator inspection. Report only status, item count and
whether a known safe test message is recognized; keep identifiers and metadata
private. No pagination, automatic retry, attachment request, Analyze/AI or
separate application-token renewal. The same possible Key Vault credential,
PostgreSQL reauthorization-status and telemetry effects apply. This follow-up
has not been approved or executed. XLSX attachment existence/safety will still
require a separately scoped validation after a candidate message is identified.

## 41. Second bounded mailbox-list approval

The operator separately approved one additional identical mailbox-list GET using
the existing authenticated application session, including only the stated
request-driven credential-lifecycle and telemetry effects. No automatic retry,
pagination, attachment retrieval, Analyze/AI, Send or follow-up mutation is
authorized. JSON may be retained only in browser memory for private inspection;
shared evidence is limited to HTTP status, returned item count and operator
recognition of a safe test message. Tokens, connector IDs, headers and message
contents must not be exposed. Browser execution remains operator-assisted;
this second request's execution and result are pending, not claimed complete.

## 42. Second attempt blocked at CORS preflight

The operator reports that the second attempt used copied fetch option
`credentials: "include"` and was blocked at preflight because the response lacked
`Access-Control-Allow-Credentials: true`. No mailbox-list response was obtained;
no Analyze/AI occurred. This attempt does not supersede the first request's
operator-observed HTTP 200. No successful second GET or credential write is
claimed; preflight telemetry may exist.

Local source inspection confirms `app/main.py` configures CORS with
`allow_credentials=False` and allows the Authorization header. API authentication
reads the explicit bearer header; the frontend client supplies that header and
does not set credentials to include. The appropriate operator fetch correction
is `credentials: "omit"`, preserving the private explicit bearer header, CORS
mode and redirect-error behavior. No backend CORS change is proposed.

One corrected bounded GET to the same mailbox-list URL is proposed, with JSON
retained in browser memory and only status/count/operator recognition shared.
Fresh individual approval is required before execution, including the previously
stated credential-lifecycle and telemetry effects. No retry, pagination,
attachment retrieval, Analyze/AI, Send, separate application-token renewal or
follow-up mutation is authorized by this proposal. No corrected request issued.

## 43. Corrected mailbox-list request approved

The operator explicitly approved one corrected GET with `credentials: "omit"`,
`mode: "cors"`, and `redirect: "error"`, retaining the existing bearer header
privately. Approval includes request-driven Key Vault credential updates,
PostgreSQL connector reauthorization-status updates on permanent refresh failure,
and normal telemetry only. No retries, pagination, attachment retrieval,
Analyze/AI, Send, separate application-token renewal or follow-up mutation.
JSON must remain in browser memory; shared results are limited to HTTP status,
item count and safe-test-message recognition (yes/no/uncertain).
Operator-assisted execution and results remain pending; no corrected GET has
been issued by the agent and no new live success is claimed.

## 44. Corrected CORS passed; application authentication rejected

Operator-observed result: corrected CORS preflight HTTP 200; actual mailbox-list
GET HTTP 401 Unauthorized. No retry, mailbox response, attachment retrieval,
Analyze/AI or Send. Token expiry is a hypothesis, not verified evidence. The
approved corrected attempt is complete; further authentication or mailbox
requests require fresh approval. Earlier first-list HTTP 200 remains historical.

Local authentication review: the app uses `acquireTokenSilent` with the current
application account and configured ECI API scopes; MSAL caches in sessionStorage.
The instance is module-local, not a documented browser global. A single isolated
silent acquisition is the minimal proposed authentication operation, retaining
its result privately and stopping on interaction-required/error. It may update
the browser token cache and Entra session/audit state. No mailbox credential
operation or ECI API call is included. Execution must first establish access to
the existing instance/configuration without reload or triggering application
queries; do not invent a `window.msalInstance` or extract refresh tokens.

No login, token acquisition, reload or further mailbox request performed. An
uncontrolled reload is not proposed because mounting the app can trigger token
acquisition and application queries. Any fallback requiring reload or interactive
login needs its own concrete scope and approval. Phase 21 remains OPEN.

## 45. Conditional silent-acquisition approval; access blocked

The operator approved one isolated `acquireTokenSilent` for the existing ECI
application account/scopes only if the existing MSAL instance can be accessed
without other application requests. Permitted effects: browser session-storage
token-cache updates and Entra authentication/session/audit records. Interactive
fallback, reload, ECI API/mailbox requests, automatic retries and token exposure
are prohibited; stop if safe access is unavailable or interaction is required.

Tool availability rechecked: no browser/DevTools control tool is exposed. Source
`frontend/src/main.tsx` creates the instance locally and passes it through React;
it does not establish a console-accessible global. No existing browser debugging
reference to that instance has been supplied or verified. Safe access cannot be
established from this agent session, so the conditional operation was not invoked.
This is an access blocker, not an MSAL interaction-required response or evidence
that renewal failed. No token printed, login, reload, API/mailbox request or
cloud mutation performed. Stop at this checkpoint; Azure acceptance incomplete,
AWS mutation not started, Phase 21G BLOCKED and overall Phase 21 OPEN.

## 46. Operator restored session; exposed application token

The operator reports reloading Azure ECI independently: `/api/v1/me` HTTP 200,
`GET /api/v1/connector-accounts?limit=20&offset=0` HTTP 200 and its preflight HTTP
200. This establishes operator-observed restored application authentication and
owned-connector listing; it is not another mailbox-list result. The operator
reports the current bearer token was visible in a screenshot. Treat it as exposed;
do not request, copy, reuse, print or retain it in reports. No token value received
or reproduced by the agent in this checkpoint.

An isolated forced silent renewal still lacks a verified safe reference to the
existing browser MSAL instance. The practical supported recovery proposal is the
application's normal sign-out followed by a separately approved fresh sign-in,
keeping ECI API traffic blocked in browser DevTools during authentication so
automatic app queries cannot consume mailbox authority. Native sign-out invokes
`logoutRedirect` and clears the relevant MSAL cache, with Entra session/audit
effects and return navigation. Fresh sign-in and later mailbox GET each require
their own approval. Tokens should remain managed by MSAL, not copied into fetch
commands or screenshots. Sign-out/fresh issuance must not be described as proof
that the exposed access token is revoked; no revocation operation is proposed
or performed here. Recovery proposal pending approval; no agent authentication,
reload, mailbox request or cloud mutation performed.

## 47. Sign-out-only approval; operator execution pending

The operator approved blocking the Azure API hostname in browser DevTools first,
then clicking ECI Sign out once, allowing normal authentication redirects and
stopping at the signed-out screen. Permitted effects are relevant browser/MSAL
cache clearing and normal Entra sign-out/session/audit activity. No sign-in,
ECI API request, mailbox request, reuse of the exposed bearer token or additional
authentication action is authorized. No browser-control tool is available to the
agent; these steps require operator execution. Approval is recorded, but API
blocking, sign-out completion and cache clearing are not yet verified. No token
value requested or retained; no agent cloud/application mutation performed.

## 48. Sign-out completed; fresh sign-in proposal

The operator confirms Azure ECI's signed-out screen is visible and browser API
request blocking remains enabled for
`*://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io/*`.
No sign-in has been performed. This is operator-observed sign-out completion,
not proof that the previously exposed access token has been revoked.

Next proposed separately approved action: keep API blocking enabled and DevTools
open, click ECI Sign in once, authenticate as the same existing ECI application
account, and allow the normal Entra redirects and MSAL startup/token acquisition
for configured ECI API scopes. Stop after return to ECI. Expected effects are
fresh browser/MSAL authentication cache and Entra session/audit updates. The
application may attempt startup API reads, but the browser block must prevent
them from reaching Azure; API-dependent error states are not a reason to unblock
or retry. No mailbox request, mailbox reconnection, Analyze/AI, Send, manual token
copy/display, scope expansion or removal of API blocking is included. Sign-in
approval and execution remain pending. No cloud/application action performed
by the agent; Phase 21 remains OPEN.

## 49. Fresh sign-in approved; operator execution pending

The operator approved fresh ECI sign-in only: keep DevTools open and the Azure
API blocking rule enabled, click Sign in once, authenticate with the same existing
ECI application account, allow normal Entra redirects and MSAL token acquisition,
and stop immediately after return to ECI. Approved effects are browser/MSAL cache
updates and Entra authentication/session/audit records. Do not unblock the API,
retry blocked startup requests, access the mailbox, copy/display tokens, invoke
Analyze/AI, Send or any additional action. No browser-control capability is
available to the agent; execution remains operator-assisted and completion is
not yet verified. No agent authentication or application request performed.

## 50. Fresh sign-in completed with API blocked

The operator confirms return to Azure ECI signed in as the same existing
application account. Azure API blocking remains enabled; startup `/me` and
`/connector-accounts` requests were blocked as intended and mailbox connections
show the expected load error. No API request was allowed after sign-in; no
mailbox access, Analyze/AI, Send or token inspection occurred. This proves
operator-observed sign-in completion, not fresh-token acceptance by the ECI API.
Display identity is not an authorization key. No token value recorded.

Next proposed separately approved operation: restore home-page identity and
connector metadata through one controlled reload at `/`, using native MSAL token
handling. Before disabling the whole-host block, enable a narrower block for
the same host's `/api/v1/connector-accounts/*` paths, which covers mailbox and
connector-specific mutation endpoints while permitting the collection query.
Keep DevTools open. Permit normal home-page GET `/api/v1/me` and GET
`/api/v1/connector-accounts?limit=20&offset=0` with any required preflights and
normal MSAL acquisition; stop after their results. No mailbox navigation,
connection/reconnection, API-status button, other product action or manual retry.
Source review finds no automatic mailbox request on the home route and query
retries disabled. This source evidence is not a new deployed-frontend attestation;
unexpected behavior must stop the procedure. Possible effects: browser/MSAL and
Entra cache/session/audit updates plus API telemetry; metadata endpoints do not
resolve mailbox credentials or write business state. Approval/execution pending.

## 51. Controlled metadata restoration approved

The operator approved enabling the narrower Azure API block for
`/api/v1/connector-accounts/*` first, disabling the whole-host block, then
reloading the ECI home route once. Authorized requests are normal startup GET
`/api/v1/me` and GET `/api/v1/connector-accounts?limit=20&offset=0`, required
preflights and normal MSAL acquisition. Approved effects: MSAL cache/session
updates, Entra authentication/session/audit activity and normal API telemetry.
Mailbox navigation, `/messages`, attachment retrieval, Analyze/AI, Send, failed
request retries and other application-data mutations remain prohibited. Stop
after startup results and report status only. No browser control is available
to the agent; operator execution/results remain pending. No restoration request
was issued by the agent and no new API success is claimed.

## 52. Fresh-session metadata restored; native mailbox-list proposal

The operator confirms controlled reload completed: GET `/api/v1/me` HTTP 200 and
GET `/api/v1/connector-accounts?limit=20&offset=0` HTTP 200. Same application login,
Platform Owner role and Active / mailbox available Outlook metadata are visible.
The connector-specific browser block remains enabled. No `/messages`, attachment
retrieval, Analyze/AI, Send or other application-data mutation occurred. This
establishes fresh-session API acceptance via operator evidence, not live mailbox
token validity or XLSX acceptance. No token value inspected or recorded.

Next proposed action is one native Open mailbox navigation for this verified
owned Outlook connector, obtaining one initial page of ten message metadata items
with MSAL-managed authentication. Before disabling the connector-specific block,
enable a same-host `/api/v1/connector-accounts/*/messages/*` block to keep message
subroutes (attachment listing and Analyze) blocked. Source inspection finds
initial selected message is null; attachment/history requests require selection,
and listing retry/reconnect/window-focus refetches are disabled. Native mounting
can also perform read-only connector metadata and platform-health reads, which
must be explicitly included in approval along with required preflights and normal
MSAL acquisition. No message selection, refresh, Load more, retry, Analyze or
Send. Stop after first list result; re-enable the broader connector-specific
block. Possible effects include Key Vault mailbox credential refresh/update,
PostgreSQL reauthorization status on permanent refresh failure, MSAL/Entra
cache/session/audit updates and telemetry. Only status, item count and safe-test
message recognition should be shared; metadata remains private in the browser.
Approval/execution pending; no new mailbox request issued by the agent.

## 53. Native mailbox-list operation approved

The operator approved enabling the message-subroute block first, disabling the
broader connector-specific block only as needed, and clicking Open mailbox once.
Allowed requests: one initial GET `/messages?page_size=10` for the verified owned
connector, required preflights, normal connector metadata reads, `/api/v1/health`
if triggered, and normal MSAL acquisition. Approved effects: mailbox credential
updates in Key Vault, connector reauthorization status on permanent refresh
failure, MSAL/Entra session updates and telemetry. No message selection,
attachment-byte retrieval, pagination, mailbox refresh, automatic retry,
Analyze/AI, Send or follow-up mutation. Re-enable the broader connector-specific
block after the result. Shared evidence is restricted to HTTP status, item count
and safe-test-message recognition. Operator execution/result pending; the agent
has no browser-control access and has issued no mailbox request.

## 54. Native Azure mailbox listing PASS

Operator verifies native GET `/messages?page_size=10` HTTP 200, ten returned
items and recognition of at least one safe test message suitable for XLSX
validation. The broader connector-specific DevTools block has been re-enabled.
No message selected, attachment retrieved, Analyze/AI or Send performed. This
establishes live mailbox listing and a privately recognized candidate, not
attachment existence/type/safety or scanner/AI acceptance. No message contents,
identifiers or tokens recorded.

Next separately proposed operation: select exactly that existing candidate from
the currently loaded list and allow one metadata-only GET
`/api/v1/connector-accounts/{owned_connector_id}/messages/attachments?provider_message_id={encoded_message_id}`.
Native selection also initiates the owned, message-filtered attachment-analysis
history GET with limit 20 and offset 0; include this read explicitly in approval.
No full message-body fetch is needed. Source review confirms selected-message
state starts null, attachment/history hooks require selection, Analyze remains
an explicit mutation, and Add to Context reads remain disabled until its panel
is opened. No context interaction is proposed.

Before disabling the two existing connector/messages-subroute blocks, enable
same-host `/api/v1/connector-accounts/*/messages?*` and `/api/v1/*/analyze*`
blocks to prevent further mailbox pages and both Analyze endpoints. Permit
required preflights and normal MSAL acquisition only with this operation; no
retry, refresh, other selection, pagination or Send. Re-enable the broader
connector block after the metadata result. Listing may update mailbox
credentials in Key Vault or reauthorization status on permanent refresh failure;
MSAL/Entra cache/session and normal telemetry effects also apply. Attachment
history reads existing owned records, without provider mailbox/AI I/O. No raw
attachment bytes, parser/scanner/AI processing, analysis creation or business
state mutation is proposed. Report sanitized HTTP statuses/count, XLSX presence,
candidate extension/MIME/reported bytes/inline status and metadata truncation;
keep message/attachment IDs, subject, sender and private filename locally.
Approval and execution pending. Phase 21 remains OPEN.

## 55. Single-message attachment metadata operation approved

The operator approved selecting only the one recognized safe message after
enabling same-host `/api/v1/connector-accounts/*/messages?*` and
`/api/v1/*/analyze*` blocks. Allowed: that message's attachment metadata listing,
supporting read-only attachment-analysis history, required preflights and normal
MSAL acquisition. Approved effects: Key Vault mailbox credential updates,
connector reauthorization status on permanent refresh failure, MSAL/Entra session
updates and normal telemetry. No attachment bytes, Analyze/AI, another message
selection, pagination, automatic retry, BusinessContext interaction, Send or
follow-up mutation. Restore the broader connector-specific block after results.
Report only HTTP statuses, attachment count, XLSX presence, candidate extension,
MIME, reported size, inline status and metadata truncation. Identifiers and
private filenames remain in the browser. Execution/results remain pending;
the agent has no browser-control access and has issued no attachment request.

## 56. Attachment metadata attempt blocked by retained browser rule

Operator reports selecting the recognized message once; the attachment area
displayed “Attachment details could not be loaded”. The retained same-host
`/api/v1/connector-accounts/*/messages/*` DevTools rule matched the intended
`/messages/attachments` metadata endpoint. This is a failed operator-controlled
validation attempt, not evidence of an API/parser failure. No attachment-list
HTTP status or history result supplied; neither is inferred. No attachment bytes,
Analyze/AI or retry; broader connector-specific block restored.

Corrected proposal, pending fresh approval: keep the same message selected,
enable only the intended protective same-host mailbox-list-query
`/api/v1/connector-accounts/*/messages?*` and Analyze `/api/v1/*/analyze*` blocks
for these paths, and explicitly disable all overlapping whole-host,
connector-specific and `/messages/*` blocks during the one request. A narrower
block is not an exception to another enabled broad block. Keep DevTools open;
do not send a test request to verify the configuration.

Use only the attachment area's retry control once. Source handler calls
`attachmentsQuery.refetch()` for the already selected message; it does not
reselect the message, refetch history or refresh the mailbox. Authorize one
metadata GET, necessary preflights and normal MSAL acquisition only; no new
history request is needed for this retry. Same credential-lifecycle, MSAL/Entra
and telemetry effects require fresh approval. Restore the broader connector
block immediately after success or failure. No second retry, reload, other
selection, attachment bytes, Analyze/AI, BusinessContext interaction or Send.
If the expected attachment-only retry control is absent, stop. No corrected
retry authorized or executed at this checkpoint.

## 57. Corrected attachment-metadata retry approved

The operator approved one attachment-area retry for the same selected message.
Keep same-host `/api/v1/connector-accounts/*/messages?*` and
`/api/v1/*/analyze*` blocking enabled; temporarily disable the overlapping
whole-host, broader connector-specific and `/messages/*` blocks. Scope is one
attachment-metadata GET, required preflights and normal MSAL acquisition.
Approved effects: Key Vault credential updates, connector reauthorization status
on permanent refresh failure, MSAL/Entra session updates and telemetry. No message
reselection, second retry, attachment bytes, Analyze/AI, pagination,
BusinessContext interaction, Send or follow-up mutation. Restore the broader
connector block after success or failure; stop if the attachment retry control
is absent. Operator execution/results pending; no browser-control access exists
for the agent, and no retry has been issued by the agent.

## 58. Azure XLSX attachment metadata PASS (2026-09-21)

Operator confirms attachment metadata GET HTTP 200 for the selected safe message:
one attachment, `.xlsx`, MIME
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, reported
size 26,883 bytes, inline false, metadata truncation false. Broader connector
block restored; Analyze remains blocked. No attachment bytes retrieved,
Analyze/AI or Send. No identifiers/private filename retained. Attachment-history
HTTP result remains unreported. This validates metadata only, not actual byte
size, container validity, scan result, extraction or provider acceptance.

## 59. Explicit XLSX Analyze proposal and frontend prerequisite

Proposed consequential request, not approved/executed:
POST `/api/v1/connector-accounts/{owned_connector_id}/messages/attachments/analyze`
with JSON `provider_message_id` and `provider_attachment_id` referencing only the
selected message and its one verified XLSX candidate. Identifiers remain private.
One explicit request, no retry. Backend verifies application identity/ownership
and connector usability, fetches the source message, validates attachment
provenance, retrieves the selected attachment, enforces size gates, requires
scanner CLEAN, validates XLSX, performs bounded extraction and Foundry tabular
inference, validates output, then commits the existing attachment-history row.

Expected durable effect on success: one new owned `attachment_analyses` row,
including provenance, filename/MIME/kind, validated structured `tabular_result`,
compatibility summary/classification, warnings/truncation and analysis metadata.
The summary may contain selected business information. No raw workbook/extracted
grid/prompt/raw provider response is stored by application persistence; provider
service-side retention has not been independently verified. Foundry inference
incurs usage; existing credential-lifecycle, MSAL/Entra and telemetry effects
apply. No workflow, BusinessContext, task/deadline/obligation or Send mutation.
Failure before commit should create no analysis row; timeout/response loss after
commit is ambiguous, so never retry without checking persistence first.

Native Analyze success invalidates the message-filtered attachment-history query;
include that supporting read, preflights/MSAL and possible connector-status read
on reauthorization failure in an eventual execution approval. Correlate sanitized
logs: scan CLEAN before parse completion, AI start/completion, persistence. Check
HTTP 200, kind xlsx, Foundry provider, non-null structured result, separate
warnings/limitations and truncation flags; match private analysis ID in history.
HTTP success alone does not prove all logging/resource/ownership acceptance.

Known prerequisite: last recorded deployed frontend is Phase 20; baseline
`frontend/src/lib/attachmentType.ts` excludes XLSX and its native attachment UI
does not offer Analyze for it. Local Phase 21 changes do not prove deployed UI
readiness. Do not enable a disabled control, copy tokens, improvise a direct
authenticated request or deploy the frontend under Analyze approval. If the
currently displayed XLSX has no enabled native Analyze control, stop and prepare
the separately approved Phase 21 frontend deployment before native execution.
Keep current blocks while approval/readiness is unresolved. No new cloud action
or Analyze performed; Phase 21 remains OPEN.

## 60. Conditional XLSX Analyze approved; native UI prerequisite unresolved

The operator approved one explicit Analyze of the verified XLSX only if the
currently deployed Azure frontend exposes an enabled native XLSX Analyze control.
Scope includes ownership/provenance, selected attachment retrieval, CLEAN scanner
gate, bounded XLSX extraction, one live Foundry inference, one validated
attachment-analysis result on success, supporting history/status reads and
normal credential/session/telemetry effects. Required evidence: HTTP 200, xlsx,
Foundry, populated tabular_result, separate warnings/limitations, truncation,
matching analysis ID in history, and sanitized scan-before-parse/AI/persist logs.
No second Analyze, retry after ambiguous outcome before persistence inspection,
BusinessContext/workflow/task/deadline/obligation state, Send or token/UI bypass.

No browser-control access exists to verify the currently rendered control.
Report review still records Phase 20 frontend and no Phase 21 frontend upload.
Therefore native UI readiness is unverified and execution remains stopped; keep
current request blocks. Operator may inspect the already rendered attachment
without clicking, reloading or issuing a request. If its XLSX Analyze control is
absent/disabled, stop and obtain separate Phase 21 frontend deployment approval.
The conditional approval is not frontend deployment authorization. No Analyze,
attachment-content retrieval, Foundry call or result persistence was performed
by the agent at this checkpoint; the approved operation remains unexecuted.

## 61. Native XLSX Analyze blocked by Phase 20 frontend

Operator confirms the selected verified XLSX displays “Unsupported for analysis”.
The conditional native Analyze prerequisite is not met. No Analyze, attachment
retrieval or Foundry invocation occurred. No manual API/token bypass is allowed.
The operator requested preparation of the existing Azure frontend deployment,
with separate approval before upload. Backend/database/AWS changes are excluded.

## 62. Azure frontend deployment prepared, not executed (2026-09-21)

Fresh read-only Azure verification: account `h.susanta@hotmail.com`, subscription
`ECI-Development` Enabled. Existing SWA `eci-web-dev`, resource group
`rg-eci-deploy-dev`, Free SKU, deployment provider SwaCli. Production/default
environment Ready, last updated `2026-09-18T23:44:40.302992+00:00`. No source branch
or repository version is recorded in SWA; do not invent a deployed Git SHA.

Public HTML/JS fetched without executing the application or calling the API:

- Host: `witty-island-03f5de51e.7.azurestaticapps.net`.
- HTTP 200; HTML SHA-256
  `e0d190e062de95ee9e0056837f868d6d23e84d120fd3918017e0abd5544276ac`.
- Current JS: `/assets/index-U3SWQ2gP.js`, 664,498 bytes, SHA-256
  `2fb511b5539b81c3e9ec0d19ffeb322d8de4599a7d7f5ca707f4361fbca7309b`.
- Current CSS: `/assets/index-CQm-ji_O.css`.
- Current JS lacks `Excel workbook (.xlsx)` and `tabular_result` markers,
  consistent with known Phase 20 and operator Unsupported observation.
- HTML cache: `public, must-revalidate, max-age=30`; ETag `"81397832"`;
  Last-Modified Fri, 18 Sep 2026 23:44:40 GMT.

Prepared artifact: existing `.phase21g-artifacts/frontend-azure/` from the successful
Phase 21G `build:azure`; baseline `63669ec` plus preserved uncommitted Phase 21
implementation. No rebuild, dependency installation or test rerun performed.
All six Azure files match `.phase21g-artifacts/frontend-sha256.json` exactly.
Target JS `/assets/index-BQKDgcbq.js`, SHA-256
`00dc87b6ecc7f1534e05e1803cafb849cd4d562b6ff62c0da20e0ff72064c1c0`.
Target HTML SHA-256
`230b9638c3e0da7b91acb808d3577196efe74986e500ac6ece9244615d4ba965`.
XLSX UI/tabular-result markers present; Azure API target present; AWS API target
absent. Static configuration matches both source and baseline, retaining SPA
fallback, MIME and security headers. No API/function/database artifacts included.

Existing local SWA CLI 2.0.10 is cached at the path below. Source inspection
confirms token-environment authentication targets the existing app and explicit
empty API/data-API locations exclude those uploads. Upload uses the same
deployment-token/SWA CLI mechanism as `.github/workflows/deploy.yml`, with no
GitHub workflow invocation (which would omit uncommitted Phase 21 work).

Exact proposed command from repository root, ONLY after individual approval:

```sh
(
  set +x
  set -eu
  cd .phase21g-artifacts/frontend-azure
  export SWA_CLI_DEBUG=log
  SWA_CLI_DEPLOYMENT_TOKEN="$(az staticwebapp secrets list \
    --subscription ECI-Development \
    --name eci-web-dev --resource-group rg-eci-deploy-dev \
    --query properties.apiKey --output tsv --only-show-errors)"
  test -n "$SWA_CLI_DEPLOYMENT_TOKEN"
  export SWA_CLI_DEPLOYMENT_TOKEN
  node /home/home/.npm/_npx/bc929ef4963a6f17/node_modules/@azure/static-web-apps-cli/dist/cli/bin.js \
    deploy . --env production --app-location . --swa-config-location . \
    --api-location "" --data-api-location "" --verbose log
)
```

Deployment credential will be read into process memory/environment only, never
printed or saved; no token retrieval has occurred during preparation. No verbose
secret logging, token reset, resource creation, CLI login or persistent command
approval. Verify target identity/state and all six hashes immediately before
execution; stop on unexpected changes. A failed/ambiguous upload requires state
inspection before any retry.

Expected cloud mutation: publish those six static files to the existing SWA's
production slot, changing served HTML/JS to Phase 21 with native XLSX Analyze and
structured tabular rendering. Existing static configuration is republished
unchanged. No backend Container App image/configuration, PostgreSQL schema/data,
AWS resource, IAM or infrastructure change; no application Analyze or mailbox
request is part of deployment. Existing resources remain running.

Azure SWA automatically handles deployment cache invalidation; no separate
CDN purge is required (Microsoft SWA FAQ:
https://learn.microsoft.com/en-us/azure/static-web-apps/faq). Hashed JS filename
changes; an already loaded browser retains old code until a later separately
controlled reload. Do not reload the authenticated browser under upload approval.
Post-upload read-only acceptance: production environment Ready, public HTML
references the new JS, served JS hash matches the approved artifact; browser
product acceptance remains separate. Deployment approval pending; nothing
uploaded and Analyze remains blocked. `git diff --check` PASS for preparation.

## 63. Approved Azure frontend upload failed; no retry (2026-09-21)

User individually approved the exact section 62 upload, existing deployment-token
retrieval/use in process only, production/default `eci-web-dev` and the six-file
artifact with target JS hash
`00dc87b6ecc7f1534e05e1803cafb849cd4d562b6ff62c0da20e0ff72064c1c0`.
No additional deployment, rebuild, backend/database/AWS/IAM/infrastructure change,
mailbox/Analyze, commit/push or authenticated-browser reload authorized.

Immediate preflight PASS: account/subscription/hostname/Free SKU/SwaCli provider
matched, production/default Ready at original September 18 timestamp, exact six
artifact files and hashes matched, whitespace check passed. The exact approved
command was executed once using SWA CLI 2.0.10. Token was captured privately in
the subshell environment, not printed or saved. CLI selected production, the
expected artifact directory and existing staticwebapp.config.json. It then
reported:

```text
Current directory cannot be identical to or contained within artifact folders.
Deployment failed with exit code 1
The deployment binary exited with code 1.
```

The proposed `cd .phase21g-artifacts/frontend-azure` was incorrect for the native
StaticSitesClient; this is the agent's preparation error, not a source/build
failure. No retry or corrective cloud mutation was performed. Do not infer that
the failed CLI means no control-plane mutation occurred.

Post-failure read-only verification:

- SWA production/default reports **Uploading** on two checks, with lastUpdatedOn
  `2026-09-20T23:22:42.988345+00:00` (September 21 local Lisbon date). It has not
  been verified back at Ready. No cancellation/reset/delete operation performed.
- Public HTML HTTP 200 still has old SHA-256
  `e0d190e062de95ee9e0056837f868d6d23e84d120fd3918017e0abd5544276ac`, references
  `/assets/index-U3SWQ2gP.js`, and retains Last-Modified September 18.
- Referenced JS HTTP 200 still has old SHA-256
  `2fb511b5539b81c3e9ec0d19ffeb322d8de4599a7d7f5ca707f4361fbca7309b`.
- Prepared artifact's six recorded hashes remain unchanged. No rebuild/test
  rerun necessary or performed. `git diff --check` PASS.

Observed scope: existing Azure SWA deployment state changed, while public Phase
20 content remains available. No backend, database, AWS, IAM or infrastructure
mutation command issued. No authenticated browser reload, mailbox access,
attachment bytes or Analyze/AI. No commit/push. Resources left running.

A future separately approved correction must run from the repository root,
outside the upload tree, remove that `cd`, and use this CLI invocation with the
same private token setup (proposal only):

```sh
node /home/home/.npm/_npx/bc929ef4963a6f17/node_modules/@azure/static-web-apps-cli/dist/cli/bin.js \
  deploy .phase21g-artifacts/frontend-azure --env production --app-location . \
  --swa-config-location .phase21g-artifacts/frontend-azure \
  --api-location "" --data-api-location "" --verbose log
```

Recheck actual SWA state before proposing/executing another upload; it may still
be processing the failed attempt. Another deployment requires fresh approval.
This approved upload attempt is consumed. Deployment result: **FAILED; serving
artifact unchanged, control-plane state unresolved (Uploading)**. Phase 21G
remains BLOCKED, overall Phase 21 OPEN. Stop before browser reload or Analyze.


## 64. Subsequent Azure completion (operator-reported; recorded 2026-09-23)

The operator supplied these subsequent successful results after the section 63
failure. This documentation pass did not query Azure, inspect new cloud logs,
repeat deployment or migration, retrieve attachments, or invoke AI.

- PostgreSQL migrated to `21d0001`; Phase 21 backend deployed successfully.
- Phase 21 frontend subsequently deployed successfully. Served bundle
  `index-BQKDgcbq.js` matched the approved artifact's SHA-256 (section 6:
  `00dc87b6ecc7f1534e05e1803cafb849cd4d562b6ff62c0da20e0ff72064c1c0`).
- Live Outlook XLSX Analyze returned **HTTP 200**, using `microsoft_foundry`.
  Structured `tabular_result` was populated; truncation was correctly detected
  and displayed; saved analysis ID matched history.
- Scanner-before-parser ordering was established through combined correlated
  logs, artifact-matched source and integration tests. This is a combined
  evidence conclusion, not a claim that logs independently prove parsing could
  not begin before CLEAN (see section 66).
- Logging privacy and side-effect isolation passed for the reviewed operation.
- ClamAV startup delay resolved without intervention. Final health and readiness
  endpoints returned **HTTP 200**.

**Azure Phase 21G: PASS.** The failed frontend deployment remains recorded in
section 63. No exact subsequent deployment command, completion timestamp, or
new SWA control-plane status is supplied here; none is inferred.

## 65. Subsequent AWS completion (operator-reported; recorded 2026-09-23)

The operator supplied the following deployment and live functional evidence.
This documentation pass did not query AWS or independently repeat these checks.

### Deployment and artifact identity

- Initial backend/frontend were Phase 20. RDS migrated successfully from
  `20c0001` to `21d0001`.
- Phase 21 backend was built from the local working tree at HEAD `63669ec`;
  `openpyxl 3.1.5` was verified inside the Docker image. HEAD identifies the
  baseline, not a committed Phase 21 release; the build includes uncommitted work.
- ECR image tag: `63669ec-p21g-20260923`.
- ECR digest:
  `sha256:53eb342a1ebb02309194800f2dc85d57bf46c490268b2c91be42b09911b8005d`.
- ECS task definition: `eci-api-dev:13`; deployment completed successfully.
  API and ClamAV containers were healthy.
- Phase 21 frontend deployed through existing S3 and CloudFront, with bundle
  `index-BsxIj7rg.js`. JavaScript, CSS and HTML hashes were verified; CloudFront
  invalidation completed. Section 6 records the prepared JavaScript hash;
  new CSS/HTML hash values are not supplied in this completion summary.

### Live functional and operational observations

- Gmail connected through normal OAuth. **One** live XLSX attachment analysis
  completed using `amazon_bedrock`, with structured `tabular_result` populated.
- Truncation was detected and displayed. Saved analysis was retrieved after a
  browser reload; only one matching saved analysis record was found.
- Correlated logs showed ClamAV CLEAN before completed parsing, parsing completion
  before Bedrock inference, and Bedrock completion before persistence.
- Correlated logs showed no workflow or Send operations. `action_items` was empty;
  `draft_reply` was absent from the history response. These observations apply
  to this operation and response, not all possible execution paths.
- Final ECS deployment: **COMPLETED**, running **1**, pending **0**.
- Final `/health`: **HTTP 200**, approximately **0.19 seconds**.
- Final `/api/v1/readiness`: **HTTP 200**, approximately **0.15 seconds**.

**AWS Phase 21G: live deployment and functional validation PASS.**

## 66. Evidence boundaries and remaining limitations

The completion evidence in sections 64–65 is the operator's manual live
validation report, supplied on 2026-09-23. It is accepted for this closure;
this documentation-only review adds no independent live verification. Earlier
agent-observed checkpoints retain their original provenance.

Live event ordering and static guarantees are distinct:

- CLEAN preceding a *completed parsing* log does not independently establish
  that parsing could not have started earlier. The stronger scanner-before-parser
  guarantee relies on the synchronous CLEAN gate in
  `app/application/services/attachment_inspection.py`, the subsequent parser call
  in `app/application/services/attachment_analysis.py`, and integration tests
  `test_scan_parse_ai_order_and_formula_is_inert` and
  `test_xlsx_scan_failure_blocks_parser_ai_and_persistence` in
  `tests/integration/test_phase21d_xlsx_analysis.py`. Azure's operator evidence
  additionally reports artifact-matched source. AWS's supplied summary does not
  include an equivalent per-source-file image hash comparison.
- Unsupported/malformed formats, malicious/encrypted workbooks, scanner failure,
  formula non-execution, external-link rejection, ownership/Platform Owner
  isolation, legacy-format regression, BusinessContext compatibility and every
  possible security case are **not claimed tested live** by these results.
  Relevant guarantees and regression coverage remain source/local-test evidence
  recorded in Phase 21A–F, not newly exercised cloud cases.
- Privacy and side-effect observations cover the reviewed logs and operations.
  Absence of workflow/Send events does not independently prove absence of every
  possible mutation or every possible sensitive log in other paths.
- AWS health/readiness timings are individual endpoint observations, not XLSX
  analysis latency or load benchmarks. No new peak-memory, sustained-load,
  concurrency, timeout/failure, or comprehensive responsive/accessibility
  measurements are supplied. The earlier non-blocking frontend bundle-size
  warning remains. This is not broad production/capacity certification.
- Raw cloud logs, credentials, tokens, workbook contents, private message data,
  generated deployment files and local artifacts are excluded from the commit.
  Sanitized artifact identifiers and this attestation are the retained evidence.

## 67. Final closure and documentation-only handoff

**PHASE 21G RESULT: PASS — Azure and AWS deployment and functional validation.**

**PHASE 21 RESULT: CLOSED for the delivered XLSX scope**, based on accepted
Phase 21A–F local validation and the operator-reported Phase 21G results above,
with the evidence limitations in section 66. The broader proposed live test
matrix from Phase 21F is not represented as exhaustively completed.

Historical validation counts remain **2,681 backend tests (including 94
PostgreSQL tests)** and **369 frontend tests across 30 files**; section 6 records
**86 focused tests** and artifact checks. No application tests, builds, XLSX
analysis, migrations or AI calls were repeated during this documentation pass.
The only Phase 21 migration remains `21d0001` (parent `20c0001`), reusing
`attachment_analyses`; both cloud databases are reported at that revision.
No new migration was created here.

Reported cloud changes across Phase 21G concern the existing Azure ACR,
PostgreSQL, Container App and Static Web App, and existing AWS RDS, ECR, ECS,
S3 and CloudFront deployment paths. **Cloud resources accessed or modified by
this documentation pass: none.** No Phase 22 work is started or authorized.

Commit preparation includes the preserved Phase 21 source, tests, migration,
packaging changes and documentation, with an explicit file inventory in
[the commit preparation report](phase_21g_commit_preparation.md). Temporary XML
reports and `.phase21g-artifacts/` are ignored. `AGENTS.md` was reviewed separately:
it is repository-wide agent policy, so it remains untracked and excluded from
this feature commit proposal, pending a separate decision. No staging, commit
or push is performed by this handoff.
