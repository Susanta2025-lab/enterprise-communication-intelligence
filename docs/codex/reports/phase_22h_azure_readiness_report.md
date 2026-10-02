# Phase 22H — Azure Deployment Readiness and Architecture Assessment

> **2026-10-02 status update:** See the [dated closure addendum](#closure-addendum--2026-10-02). Earlier assessments and limitations below retain their original chronology.

Assessment date: **2026-09-29**. **READY WITH CONDITIONS.** This is a completed readiness-only assessment, not deployment authorization. **Azure Phase 22 deployment remains NOT STARTED; live Phase 22 acceptance remains NOT RUN.**

## 1. Executive assessment

The existing Azure development environment can host Phase 22 without a new service, database, registry, identity, scanner, frontend host or API scope. Independently verified Azure PostgreSQL revision is **`21d0001`**. The exact required migration is **`21d0001 → 22b0001`**, followed by an API-image-only Container Apps release and an Azure-mode Static Web Apps release. Existing runtime settings can be reused; no Phase 22-specific configuration change was identified.

Current Azure facts are independently established here, rather than inferred from AWS: the active subscription is the intended ECI development subscription; the Phase 21 API digest remains deployed; the active revision is Healthy/ScaledToZero; PostgreSQL is Ready; SWA production is Ready and serves the byte-matched Phase 21 artifact. A new Azure frontend candidate builds successfully. Current resource configuration and local compatibility support proceeding to a separately authorized execution phase.

Conditions before consequential work: approve the exact backend artifact and release manifest; capture fresh baselines; complete and verify the approved database backup; accept the documented restoration boundaries; confirm the existing SWA deployment client; and arrange operator-controlled Entra browser acceptance. Read-only inspection is not a test of writes or recovery. Do not treat historical AWS success, local tests or Azure control-plane health as Azure Phase 22 acceptance.

## 2. Evidence sources and inspection boundaries

Reviewed [AGENTS.md](../../../AGENTS.md), [22F](phase_22f_report.md), [22G](phase_22g_report.md), [22G frontend readiness](phase_22g_frontend_readiness_report.md), [Azure runbook](../../../deployment/azure/README.md), [deployment](../../cloud/deployment.md), [authentication](../../cloud/authentication.md), [persistence](../../cloud/persistence.md), ADRs [025](../../decisions/ADR-025-browser-frontend-and-authentication-architecture.md), [026](../../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md), [030](../../decisions/ADR-030-action-deadline-and-obligation-tracking.md), [Phase 20 roadmap/history](../../roadmap/phase-20-business-context-matter-intelligence.md) and [Phase 21G report](phase_21g_report.md), including its later operator completion and earlier failed SWA upload.

Inspected the actual Dockerfile, Docker ignore rules, manual deployment workflow, Alembic environment and revision files, migration access helper, backend health/CORS/tracking contracts, frontend package/config/authentication/routes/API types/Tracking integration and environment templates. No Terraform/Bicep deployment stack was found in the applicable deployment directory; the established mechanism is controlled CLI/runbook execution, with optional manual GitHub dispatch.

| Evidence class | Meaning in this report |
|---|---|
| Current independent Azure | Existing-session ARM/Graph/ACR reads, database metadata in a read-only transaction, public SPA GETs |
| Current independent local | Actual source/config inspection, migration graph, 43 focused tests, typecheck, Azure build, artifact hashes and preservation checks |
| Historical Azure | Phase 20G PASS; Phase 21 migration/backend checkpoints; subsequent operator-reported Phase 21 frontend/XLSX PASS |
| Historical AWS/operator | Phase 22 migration/backend, W1–W8 and scoped frontend/browser PASS; not rechecked and not Azure evidence |
| Unverified | New release runtime behavior, live application-user identity/roles/consent, restore execution, future publishing success and capacity under load |

No Git command was used, including status/diff. Branch, HEAD, index and tracked/untracked status were not independently inspected. Actual files and hashes were inspected instead. Before validation, **953 existing files** were hashed, excluding Git internals, dependency/cache directories and credential directories. Existing implementation, migrations, reports and build artifacts were preserved. No task/specification conflict was found; older retained-state descriptions are explicitly historical, not current claims.

The existing session was used without login, tenant/subscription switch or alternative identity. Initial Azure CLI execution failed because its local session file was read-only in the sandbox; approved escalation allowed the same read operation and normal CLI local session bookkeeping. No credential cache was inspected or copied. Public SPA DNS similarly required network escalation. No backend HTTP request or live console stream was sent: those could awaken the observed zero-replica app. No mailbox, attachment, AI, Send, candidate or Work Item operation occurred.

## 3. Existing Azure resource inventory

`az account show` reported **ECI-Development**, Enabled, default, user identity. The subscription identifier was compared in memory with the historical approved Azure migration target; the resource group's subscription matched. Tenant and account identifiers were inspected through CLI metadata and omitted here. Graph `/me` via `az ad signed-in-user show` resolved the current session principal. Its tenant UPN uses an `#EXT#` alias and differs from the CLI login label; string equality of these display identifiers is not used for identity or application authorization. The infrastructure tenant differs from the frontend application tenant; no switch was attempted.

Resource group **`rg-eci-deploy-dev`**, location **spaincentral**, provisioning **Succeeded**. Current inventory:

| Resource | Current observed configuration | Reuse |
|---|---|---|
| ACR `eciacrdev6c` | Basic; Succeeded; public network enabled; admin disabled; LegacyRegistryPermissions | Existing `eci-api` repository and MI pull route |
| ACA environment `eci-ca-env-dev` | Succeeded; no VNet; no dedicated workload profiles; zone redundancy false; Log Analytics destination | Existing consumption environment |
| ACA `eci-api-dev` | Succeeded; management runningStatus Running; active revision ScaledToZero, 0 replicas | Existing API and scanner containers |
| UAMI `eci-ca-identity-dev` | Attached to ACA; client selector and registry identity match | Runtime identity |
| UAMI `eci-github-deploy-dev` | Existing narrowly scoped deployment assignments below | Available delivery identity; no workflow dispatched |
| PostgreSQL `eci-pg-dev-susanta` | Ready; PostgreSQL 16; Burstable Standard_B1ms; 32 GiB Premium_LRS/P4, 120 IOPS; autogrow disabled; HA disabled | Existing database `eci` |
| SWA `eci-web-dev` | Free; West US 2; provider SwaCli; no linked repository/branch; no custom domains; production/default Ready | Existing global static host |
| Key Vault `eci-kv-oauth-dev-susanta` | RBAC enabled; soft delete true; public network enabled; purgeProtection returned null | Existing mailbox credential store; no secret contents accessed |
| Log Analytics `eci-law-dev` | PerGB2018; 30-day retention; dailyQuotaGb -1 | Existing application/platform logs; no raw logs queried |

Existing supporting Foundry deployment in **`rg-eci-dev`** was inspected by metadata only: account `eci-foundry-dev-susanta`, project reference `eci-project-dev`, deployment `eci-gpt-54-mini`, Succeeded, model `gpt-5.4-mini` version `2026-03-17`, DataZoneStandard capacity 10. This is configuration evidence, not inference/access/performance proof. No full unrelated-resource inventory was requested in that group.

Current runtime UAMI assignments: **AcrPull** on `eciacrdev6c`, **Foundry User** on the Foundry account, **Key Vault Secrets Officer** on the existing vault. Current Graph session principal assignments include subscription **Owner**, ACR **AcrPush**, project Foundry User and vault Secrets Officer. The existing deploy UAMI has ACR AcrPush/Reader, Container Apps Contributor on `eci-api-dev`, Website Contributor and ECI Static Web App Deployment Token Reader on `eci-web-dev`. These are observed assignments, not proof that every future operation bypasses policy/deny constraints. No permission expansion is proposed. Operator cloud privileges confer no ECI application-user role.

## 4. Current deployment baseline

| Item | Independently observed baseline |
|---|---|
| API image | `eciacrdev6c.azurecr.io/eci-api@sha256:718933ccde31a4d8caf88079e50312c3d13204b604e915d5818abba34d4bf9cb` |
| ACR tag | `eci-api:63669ec-p21g-20260920`; resolves to that digest; created/updated `2026-09-20T08:25:55.8701632Z` |
| Revision | `eci-api-dev--p21g-63669ec-20260920`; latest = latest-ready; active, Healthy, ScaledToZero; created `2026-09-20T11:58:38Z` |
| Rollout mode | Single; latest receives 100%; min/max replicas 0/1; cooldown 300 s, polling 30 s |
| Revision inventory | One revision returned. Older historical revisions must not be assumed recoverable. |
| API resources | Container `eci-api-dev`, 0.5 CPU / 1 GiB, 2 Gi ephemeral storage; no explicit probes returned |
| Scanner | Container `clamav`, `eciacrdev6c.azurecr.io/eci-clamav:1.4-b25d9199257a`, 1 CPU / 2 GiB, 4 Gi ephemeral storage |
| Scanner probes | TCP 3310 readiness: delay 10 s, period 10 s, timeout 5 s, failure threshold 6; startup: delay 10 s, period 60 s, timeout 10 s, failure threshold 10 |
| API URL | `https://eci-api-dev.politestone-fb9d0321.spaincentral.azurecontainerapps.io` |
| Ingress | External, target 8000, allowInsecure false, transport Auto; no custom domain, IP restriction, additional public port or ingress CORS policy returned |
| Frontend URL | `https://witty-island-03f5de51e.7.azurestaticapps.net` |
| SWA environment | default/Ready; lastUpdatedOn `2026-09-20T23:57:03.555321Z` |
| Live schema | `21d0001`, database `eci`; Context and attachment-analysis tables present; three Phase 22 tables absent |

Compared with Phase 20G, backend image/revision, schema and frontend release have changed to Phase 21. Compared with Phase 21G, the image and public frontend hashes match recorded artifacts, and the historical failed-upload/Uploading state is now independently Ready. The report does not infer a missing operator upload timestamp from this metadata. No historical configuration snapshot permits a complete all-property drift audit.

The API's management runningStatus does not mean a serving replica currently exists. Health/readiness HTTP and scanner CLEAN are **NOT VERIFIED in 22H**. Database readiness alone does not prove migration head; head was queried separately. Native restart/revision facilities exist, but no restart/activation/copy/update was performed. Use a new revision pinned to the preserved image for rollback if the previous revision is unavailable; do not rely on changing traffic in the current Single mode. [Microsoft revision documentation](https://learn.microsoft.com/en-us/azure/container-apps/revisions).

## 5. PostgreSQL migration readiness and exact proposed path

Historical Phase 20G revision: **`20c0001`**. Historical Phase 21G migration and operator closure: **`21d0001`**. Current independent read-only verification: **`21d0001`**. Local sole head: **`22b0001`**, parent `21d0001`; no branch or additional dependency.

Relevant graph:

```text
19b0001 → 20b0001 → 20c0001 → 21d0001 → 22b0001
           contexts   links      XLSX      tracking
```

Local `python -m alembic heads` and `python -m alembic history` succeeded. The full earlier chain is linear: base → 9a0001 → 10b0001 → 11b0001 → 12a0001 → 13a0001 → 16f0001 → 18d0001 → 19b0001. **Do not rerun Phase 20/21 migration commands on this verified database.** If fresh preflight differs, stop: a predecessor would need its remaining graph suffix, `22b0001` would need no migration, and an unknown/multiple revision requires reconciliation. Do not stamp the database.

The live query reused the approved Phase 21G mechanism: the existing ACA `database-url` secret was retrieved into process memory only, validated as `postgresql+psycopg` to the exact Azure host/database with required TLS, then used with `default_transaction_read_only=on`, 10-second connect/statement timeouts and 3-second lock timeout. `SHOW transaction_read_only` returned `on`; `current_database()` was `eci`. Only Alembic/schema/privilege metadata was selected. The transaction was rolled back and the connection disposed. No business rows, connection string or credentials were output, stored or passed on the command line. The historical migration helper was inspected, **not executed**: its predecessor/head guards and business-row fingerprint queries are inappropriate for this assessment.

Observed database privileges through that existing connection: CONNECT, public schema USAGE/CREATE, REFERENCES on users/contexts and UPDATE on alembic_version are true. The established credential therefore has broader rights than read-only, but this session enforced read-only transactions. A separately selected migration role needs these DDL/reference rights, index/constraint creation and Alembic version-table access; runtime needs DML on the new tables. If migration and runtime roles differ, explicitly verify new-table grants/default privileges. Their ownership/default-grant separation was not fully audited; do not assume an application Entra token authenticates to PostgreSQL. Server password authentication is enabled and Entra database authentication disabled.

| Revision | Actual migration changes | Retention/rollback implications |
|---|---|---|
| `20b0001` (already applied) | Creates business_contexts, owner cascade FK, type/status/archive checks, two indexes | Downgrade drops contexts; not a Phase 22 recovery step |
| `20c0001` (already applied) | Creates communication links, context/owner FKs, unique context/connector/message, two indexes | Downgrade drops associations; not authorized |
| `21d0001` (already applied) | Adds nullable JSONB tabular_result to attachment_analyses and broadens kind check for xlsx | No parallel XLSX store; downgrade refuses XLSX rows, otherwise drops column |
| `22b0001` (required) | Creates three tables, 47 columns, six explicit indexes, 24 CHECK declarations, five UNIQUE declarations, four FK declarations and three primary keys | Additive; no historical data rewrite/backfill/delete; populated downgrade deliberately refused |

Migration file SHA-256: **`62479537c12b48004cb5f09f36733b77b42314d03b9e6ccf49119f2669ea2612`**.

New schema inventory:

| Table | Columns | Principal constraints/indexes |
|---|---|---|
| business_work_items | id, user_id, kind, status, title, description, business_context_id, due_kind, due_date, due_at, due_timezone, completed_at, cancelled_at, archived_at, created_at, updated_at, version, creation_origin, confirmed_by_user_id, confirmed_at, creation_key, creation_request_hash, origin_candidate_key | Owner cascade; current context SET NULL; unique id/owner, owner/creation-key, owner/candidate-key; checks for bounded normalized text, due null combinations, terminal timestamps, version, confirmation and hashes/key characters |
| business_work_item_sources | id, work_item_id, user_id, source_kind, analysis_id, attachment_analysis_id, connector_account_id, provider_message_id, provider_attachment_id, candidate_field, candidate_index, candidate_digest, source_key, linked_at | Composite item/owner cascade FK; unique item/source-key; typed reference, locator, pair, digest and provider-ID checks; historical source IDs intentionally not cascading FKs |
| business_work_item_events | id, work_item_id, user_id, actor_user_id, event_type, occurred_at, item_version, event_ordinal, context_at_event_id, metadata | Composite item/owner cascade FK; actor=owner; valid event/version/ordinal; unique item/version/ordinal; JSONB metadata; historical context ID retained without FK |

Explicit indexes: `ix_bwi_owner_created` (user_id, created_at, id), `ix_bwi_owner_status_at` (user_id, status, due_at, id), `ix_bwi_owner_status_date` (user_id, status, due_date, id), `ix_bwi_owner_context` (user_id, business_context_id, created_at, id), `ix_bwie_owner_item` (user_id, work_item_id, occurred_at, id), `ix_bwie_owner_context` (user_id, context_at_event_id, occurred_at, id). Unique/PK indexes are additional. Source count, same-owner context, event JSON and append-only behavior also rely on application enforcement, not only SQL constraints.

Retain all Azure users, contexts, associations, analyses, attachments, credentials references and workflows. Do not import AWS data or auto-create tracking from existing AI results. UUID/text/date/timestamptz/JSONB work with existing PostgreSQL 16; no extension or capacity increase is required by this migration.

Exact later command, after backup and fresh revision/target guards: **`python -m alembic upgrade 22b0001`**. Inject the migration URL securely in process environment using the established mechanism; never put it in arguments or documentation. Apply once, independently of app startup. Alembic wraps PostgreSQL DDL/version changes in a transaction; locks and timeout/uncertain-connection outcomes still require inspection. Use reviewed lock/statement timeouts and no automatic retry. Downgrade takes ACCESS EXCLUSIVE locks on all three tables and refuses before destructive DDL if any contains data; only empty-table downgrade can drop them. It is not the routine rollback plan.

## 6. Backend compatibility and deployment requirements

The shared `python:3.12-slim` Dockerfile installs the application, runs as appuser/UID 1000, exposes 8000 and starts Uvicorn. It packages application source, not Alembic scripts. Preserve migration/startup separation. `.dockerignore` excludes environment files and recursive Python caches. Before later image build, review its actual context and package inventory; source hashes are necessary because the release remains intentionally uncommitted. Do not tag this work as though an old commit contains Phase 22.

Prepare Linux/amd64 using this Dockerfile and existing dependencies. Either independently verify an already available local Phase 22 image against the working tree and its package inventory, or build a new approved image. Do not query AWS or assume its deployed digest proves local equivalence. Use a unique `p22-azure-<UTC>-<source-manifest-prefix>` tag, preserve the old tag/digest and deploy **by registry digest**; existing ACR tags are writable/deletable. Do not overwrite `stable` or old release tags. No ACR Task/remote build is required.

Current allowlisted settings verified: production, OIDC, microsoft_foundry, communications:analyze, azure_key_vault, existing Foundry project/model, ClamAV localhost:3310/10-second timeout, image input false. DATABASE_URL references ACA secret `database-url`; Gmail/Microsoft client secrets are also ACA secret references. Those three ACA secrets are not Key Vault URL references. Key Vault is the separate runtime mailbox credential store. ACR uses the attached UAMI and no password reference.

Keep both containers and all resources/settings/identities/secret references/scale/ingress unchanged during the API-image-only update. Phase 22 Tracking uses identity and database repositories, not inference, mailbox, scanner, parser or Send services. No new Foundry configuration, Entra scope, ClamAV resource or environment variable is needed.

Docker HEALTHCHECK uses `/health`; the live ACA API template has no explicit probes, and the runbook describes platform default TCP probes. This does **not** prove HTTP database readiness. Later rollout must independently check `/health`, `/api/v1/health` and `/api/v1/readiness` plus schema and owned API access. Scanner configuration is not CLEAN proof; no live scan is required for manual Tracking validation. Preserve fail-closed attachment processing.

Existing JSON stdout/platform logging routes to Log Analytics. App diagnostic-settings list returned `[]`; the environment's Log Analytics destination remains configured. No raw console, business log records, metrics history or alerts were queried. Native requests/replica/CPU/memory/restart metrics are an available later observation route, not a new monitoring product or a current load-test result.

## 7. Frontend and authentication readiness

`npm run build:azure` is `tsc -b && vite build --mode azure`. Use existing `.env`, `.env.azure`, `.env.azure.local` precedence and operator/CI configuration, rather than the generic production build. Effective values were loaded through Vite and validated through the actual config parser in memory; no inherited VITE overrides or extra exposed keys were found. Eight intended public keys are configured.

Current candidate, public Phase 21 JavaScript and live backend configuration agree on API origin, public SPA client, authority, redirect/logout origin and all five explicit delegated scopes: communications:read/analyze/connect/workflow/send. Authority host is `eciexternaliddev.ciamlogin.com`; tenant identifiers are omitted. Backend audience matches the scopes' resource prefix, and issuer/JWKS tenant references match the frontend authority. Infrastructure tenant is different; current CLI access does not establish read access to the application tenant's Entra registrations. **Fresh registration/consent/redirect authorization was not queried and authenticated browser acceptance is NOT RUN.** No new auth change is indicated by the matching configuration and historical working registration.

MSAL remains a public client, sessionStorage auth cache, silent access-token acquisition and normal operator sign-in when required. Redirect and post-logout use the same SWA origin. `/api/v1/me` remains the server-authoritative role source; no role bootstrap is needed or authorized. Identity-bound query caches and memory-only creation recovery clear on identity change; no business drafts or mailbox credentials are added to browser storage.

Live CORS_ALLOWED_ORIGINS and FRONTEND_OAUTH_RETURN_URL exactly match the SWA origin. Source middleware disallows credentialed CORS and exposes Location. Live Phase 22 CORS response behavior remains a later gate; no ACA OPTIONS request was sent to wake the app. HTTPS ingress is configured; the SPA's public DNS/HTTPS works. No custom DNS, gateway, Front Door or certificate purchase is needed.

Local contracts are compatible: `/tracking` and `/tracking/:itemId`, owner-scoped list/filter/page/detail/events, manual creation, strict confirmation, expected-version PATCH/status/archive/restore and candidate endpoints. `archive=active` means unarchived, not status=open. Business Context's Tracking tab uses the same context-filtered API; timeline projects genuine events. Existing attachment/XLSX panels retain explicit Analyze and advisory candidate review. Candidate display does not create a Work Item. No source/API mismatch was found; live equivalence still needs the approved backend digest.

Static config rewrites SPA routes to index.html, excludes assets, supplies MIME types and sets nosniff, strict-origin-when-cross-origin, DENY and frame-ancestors 'none'. Current GET `/`, `/tracking` and a synthetic detail-shaped route returned the same Phase 21 HTML, HTTP 200, those headers and HSTS. This proves host fallback, not deployed Phase 22 rendering. TLS protocol enumeration was not performed.

Current public release: `assets/index-BQKDgcbq.js`, SHA-256 **`00dc87b6ecc7f1534e05e1803cafb849cd4d562b6ff62c0da20e0ff72064c1c0`**; index.html SHA-256 **`230b9638c3e0da7b91acb808d3577196efe74986e500ac6ece9244615d4ba965`**. Public HTML, JS, CSS, favicon and logo all byte-match the retained `.phase21g-artifacts/frontend-azure/` release. The current JS lacks the Tracking API marker; the candidate contains it and excludes the AWS API origin.

A six-file rollback candidate was preserved under `.phase22h-readiness-20260929/rollback-frontend/`. Five files are live-byte-verified. Its staticwebapp.config.json comes from the historical local artifact, matches current source, and is behaviorally corroborated by live fallback/headers; its original deployed bytes are not independently export-verified. The public `/staticwebapp.config.json` request returned **HTML fallback**, not JSON. That diagnostic response is excluded from the rollback candidate. Never publish the `public-current-frontend/` diagnostic folder wholesale.

Existing SWA publication is sufficient; no new host is needed. No `swa` executable was found on PATH. Phase 21G documents cached SWA CLI 2.0.10; its availability must be confirmed before execution, without automatic installation. Its prior failure was caused by running inside the artifact directory. Run a verified client from repository root, outside the output tree. The successful later operator upload is historical evidence; no successful command is invented from it. Do not dispatch the current GitHub workflow for uncommitted work: it checks out committed source and its frontend job is not gated on backend/migration completion.

## 8. Local validation results

New checks used existing dependencies and a new output directory. No application source was changed. Historical 22F evidence remains **3,147 backend (including 214 PostgreSQL), 473 focused backend, 429 frontend and 60 focused frontend**; overlapping suites are not additive. 22G frontend assessment also previously ran 429 frontend tests. None of those full suites was rerun here.

| Actual 22H check | Result |
|---|---|
| `python -m alembic heads` | Exit 0; sole 22b0001 |
| `python -m alembic history` | Exit 0; linear graph recorded above; no DB connection |
| `npm run typecheck` from frontend | PASS; separately captured exit 0. Initial chained invocation had no separate exit record, so repeated only to capture it. |
| `npm test -- --run src/test/config.test.ts src/test/msalConfig.test.ts src/test/deploymentBadge.test.tsx` | Exit 0; **43 passed, 3 files**, 1.88 s; offline config/auth/presentation tests |
| `npm run build:azure -- --outDir ../.phase22h-readiness-20260929/dist` | Exit 0; 344 modules; build stage 408 ms |
| Vite effective-env + actual config parser; old/new bundle setting comparison | Exit 0; intended Azure values match |
| Entry/literal JS import resolution, source maps/dotenv absence, Azure/AWS origin isolation, static config comparison | Exit 0; no missing references found; no source maps/dotenv artifacts |
| Migration AST inventory/hash | Exit 0; 3 tables/47 columns/6 indexes as above |
| Existing-file SHA-256 preservation | 953 files checked, zero changed/missing before report; final check recorded below |

Candidate: `.phase22h-readiness-20260929/dist/`, 12 files. Manifest `.phase22h-readiness-20260929/artifact-manifest.json`, SHA-256 **`7bf7e64315af98fc2a24bdf017876326d0ed83687847446ec6083d29f68e750e`**. Entry is 544 bytes, SHA-256 **`43bcfc3f1e827356a442addb198a45458a9448b09a08bdcdbc969d0080a0fd55`**. Main JS is `index-v2r-gI2A.js`. Retained non-failing warning: 513.01 kB / 141.60 kB gzip exceeds Vite's 500 kB advisory. Output-outside-project warning is expected; no emptying override was used and frontend/dist was preserved.

No backend/DB tests, dependency installs, lint/full-suite reruns, image builds or Git checks were needed for this documentation/inspection-only task. Existing test/build evidence does not certify browser behavior, cloud load, backup recovery or scanner liveness.

Read-operation command ledger (Azure commands used JSON output and safe projections or in-memory filtering; identifiers/secrets were omitted):

```text
az account show
az group show --name rg-eci-deploy-dev
az resource list -g rg-eci-deploy-dev
az containerapp show -g rg-eci-deploy-dev -n eci-api-dev
az containerapp revision list -g rg-eci-deploy-dev -n eci-api-dev
az containerapp env show -g rg-eci-deploy-dev -n eci-ca-env-dev
az postgres flexible-server show -g rg-eci-deploy-dev -n eci-pg-dev-susanta
az postgres flexible-server db list -g rg-eci-deploy-dev -s eci-pg-dev-susanta
az postgres flexible-server parameter show -g rg-eci-deploy-dev --server-name eci-pg-dev-susanta -n require_secure_transport
az postgres flexible-server firewall-rule list -g rg-eci-deploy-dev --server-name eci-pg-dev-susanta
az postgres flexible-server backup list -g rg-eci-deploy-dev --server-name eci-pg-dev-susanta
az staticwebapp show -g rg-eci-deploy-dev -n eci-web-dev
az staticwebapp environment list -g rg-eci-deploy-dev -n eci-web-dev
az acr show -g rg-eci-deploy-dev -n eciacrdev6c
az acr repository show -n eciacrdev6c --image eci-api:63669ec-p21g-20260920
az identity show -g rg-eci-deploy-dev -n eci-ca-identity-dev
az identity show -g rg-eci-deploy-dev -n eci-github-deploy-dev
az ad signed-in-user show
az role assignment list --assignee-object-id <in-memory-principal> --all
az role assignment list --assignee-object-id <in-memory-session-principal> --all --include-inherited
az keyvault show -g rg-eci-deploy-dev -n eci-kv-oauth-dev-susanta
az monitor log-analytics workspace show -g rg-eci-deploy-dev -n eci-law-dev
az monitor diagnostic-settings list --resource <in-memory-eci-api-dev-resource-id>
az cognitiveservices account deployment show -g rg-eci-dev -n eci-foundry-dev-susanta --deployment-name eci-gpt-54-mini
az containerapp secret list -g rg-eci-deploy-dev -n eci-api-dev --show-values --query "[?name=='database-url'].value | [0]"
```

The last command's result was captured privately by the read-only SQL process, never displayed. All final cloud reads exited 0; no AuthorizationFailed/permission denial occurred. Initial account sandbox failure exited 1. Two firewall and two backup attempts used unsupported `-n`/`--name` server options and each exited 2 before a cloud read; installed CLI help established `--server-name`, and corrected reads succeeded. A diagnostic-settings projection returned empty output and the local JSON wrapper exited 1; a corrected unprojected read returned `[]`, exit 0. Initial public GET failed DNS/exit 1; escalated GETs succeeded/exit 0. These are recorded inspection/tooling failures, not resource failures. Installed help for firewall list, backup list/create and restore exited 0; help did not invoke a mutation.

SQL statements were limited to `SHOW transaction_read_only`, `SELECT current_database()`, `SELECT version_num FROM alembic_version`, an allowlisted information_schema table query and has_*_privilege metadata predicates. Public HTTP used GET only on the SWA shell/deep links and six static paths. No bearer was used. Microsoft public documentation was consulted for backup/restore, revisions and billing; it establishes service semantics, not this subscription's live state.

## 9. Security and privacy considerations

Verified `(iss, sub)` → users.id → application role plus object ownership remains authoritative. Cloud Owner, mailbox identity and Platform Owner do not bypass object ownership. Current Entra configuration comparisons expose no identifiers; no token acquisition/extraction, browser cache access or application identity manufacture occurred.

Maintain explicit human creation/confirmation, advisory AI, version checks and atomic append-only events. Tracking is not workflow execution. Analyze → Propose → Approve/Reject → Execute remains separate. No automatic actions, Send, mailbox fetch or candidate confirmation is included in readiness or the default browser smoke.

Preserve metadata-only attachment listing, explicit Analyze before bytes, scanner-before-parser, bounded openpyxl, inert formulas, no external workbook resolution, no durable raw bytes and fail-closed unsupported formats. Only xlsx is supported among spreadsheet formats. Saved XLSX history remains in attachment_analyses.

Current PostgreSQL networking is public access with two single-address firewall rules (including allow-operator-migration), no 0.0.0.0 Azure-services rule, no delegated subnet/private DNS, and require_secure_transport=on. Addresses are omitted. Successful metadata connection demonstrates this operator path, not every ACA egress path; ACA-to-DB readiness must be retested later. Do not broaden firewall/IAM on failure.

## 10. Cost and resource reuse

**No new paid service or capacity increase is proposed for rollout. Numerical incremental cost estimate: unavailable.** Account-specific prices, credits, reservations, usage and currency were not obtained; no invented euro figure or zero-cost claim is made.

| Billing dimension | Current posture and likely exposure |
|---|---|
| Image preparation/ACR | Local Docker build can reuse existing route; no ACR Tasks required. Basic registry standing charge and additional image storage/transfer remain. |
| ACA | Currently 0 replicas; combined API+scanner allocation per running replica is 1.5 CPU / 3 GiB. Validation starts runtime consumption; cold starts/scanner updates/logging also matter. |
| PostgreSQL | Currently Ready, so do not assume compute is stopped. B1ms compute, 32 GiB storage and backup usage remain; no autogrow/HA increase proposed. |
| SWA | Existing Free tier; candidate uses current host. Observe tier bandwidth/storage/deployment limits; no upgrade proposed. |
| Network/identity/Key Vault | Existing public HTTPS, registry/database traffic and possible vault transactions; no gateway/private endpoint/new network product. Tracking itself needs no mailbox credential retrieval. |
| Monitoring | Existing PerGB2018 log ingestion and retained storage; 30 days, no daily ingestion cap configured. Do not add dashboards, alerts or Application Insights by implication. |
| Foundry | Existing deployment reused; **zero inference required** for the proposed manual lifecycle. No inference performed here. |
| Recovery contingency | PITR creates a separate paid PostgreSQL server and requires a separate resource/cost decision; it is not normal rollout infrastructure. |

ACA consumption/request billing and zero-replica behavior are described by [Microsoft](https://learn.microsoft.com/en-us/azure/container-apps/billing). PostgreSQL continues charging provisioned storage and excess backup storage while compute is stopped; numerical rates depend on the agreement/region. [PostgreSQL pricing](https://azure.microsoft.com/en-us/pricing/details/postgresql/flexible-server/).

During validation PostgreSQL and a serving API/scanner replica must be available; SWA remains accessible. Afterward retain min 0/max 1 and allow ordinary idle scale-to-zero. A deliberate app stop/deactivation or database stop needs later explicit instruction; temporary database stopping is not permanent cost elimination and provider restart limits must be rechecked. No resource was stopped, started, scaled or resized here. AWS state/costs were not inspected.

## 11. Proposed sequential execution plan — NOT EXECUTED

Each mutation needs a fresh explicit execution instruction covering that operation and any contingency recovery. The read-only authorization for 22H does not authorize this sequence. Use one operator and a controlled window; stop on unexpected state, failed prerequisites, credential expiry or uncertain writes.

| Step / exact target | Prerequisites and operation | Expected result / verification | Stop and recovery boundary | Fresh authority |
|---|---|---|---|---|
| 1. ECI-Development / rg-eci-deploy-dev | Repeat identity, subscription, inventory and current revision/schema reads with existing session | Same intended target; compare current facts to this baseline | Different identity/subscription/state: stop; no login/switch workaround | Include read preflight in next-phase instruction |
| 2. Existing ACA, ACR, SWA, PostgreSQL | Capture sanitized app/sidecar/secret-reference templates, digest, schema, backup window, SWA status and public hashes; preserve old artifacts | Baseline sufficient for exact image/config comparison and restoration | Drift or missing old artifact: resolve before writes | Read-only preparation |
| 3. eci-pg-dev-susanta | Quiesce application writes by approved operator procedure; create named on-demand backup; record successful completion and pre-migration UTC restore point | Backup appears in list; server Ready; recovery permissions/limits reviewed | No verified backup/restore boundary: do not migrate; do not create a recovery server preemptively | **Yes: backup and any deliberate quiescence** |
| 4. Database eci | Reassert revision 21d0001 and migration hash; run only upgrade 22b0001 once with established DDL credential | Revision 22b0001, three tables/constraints/indexes and runtime privileges verified; existing schema retained | Failure/timeout: inspect actual revision/schema; no downgrade or retry automatically; old Phase 21 code can remain on additive schema | **Yes: migration** |
| 5. Local image → eciacrdev6c/eci-api | Verify/package local uncommitted source manifest; prepare linux/amd64 image; approve digest/tag; publish once through existing AcrPush | Registry digest/platform/source inventory match; no secrets or migrations accidentally packaged | Wrong digest/dependency failure: no deployment; leave existing tags intact | **Yes: image preparation/push** |
| 6. ACA eci-api-dev, container eci-api-dev | After migration verification, update only API image to approved digest and unique suffix | New latest-ready Healthy; 100% latest; compare templates excluding image/suffix; preserve scanner/limits/MI/refs | Failed rollout/probes: inspect; use approved old-digest rollback only; no blind restart | **Yes: deployment and any rollback** |
| 7. Existing Azure API | Authorized runtime wake; GET health/readiness; operator existing Entra session GET me and work-items limit 1 | HTTP 200, expected role/capability, no CORS error; no unrelated content retained | 401/403/503 or wrong identity: stop; cloud credentials cannot replace login | **Yes: runtime/application validation scope** |
| 8. Azure-specific synthetic fixture below | Separately approve fixed identity, eight exact bodies/requests and retention; no context/source/mailbox | Versions 1–7, one item, seven events, zero sources, replay adds nothing | Any uncertain write: read-only reconciliation then stop; no new key/automatic retries/cleanup | **Yes: separate lifecycle write authorization** |
| 9. Local Azure frontend release + SWA baseline | Revalidate 12-file candidate manifest and six-file rollback candidate; verify available SWA client outside artifact folder | Exact approved bytes/config; current public baseline still matches | Changed artifact requires review; unavailable client requires explicit tooling decision, no auto-install | Artifact review and rollback acceptance |
| 10. SWA eci-web-dev production/default | Use existing token mechanism privately; publish only approved dist from repository root | Environment Ready; new index/all asset hashes+MIME verified; fallback/security headers retained | Uploading/ambiguous failure: inspect before any retry; separately authorized old-release redeploy if needed | **Yes: token use and frontend publication** |
| 11. Azure SPA/API browser | Existing authorized Entra user; read-only checklist below | Tracking/detail/history/direct reload/filter/context integration and safe recovery observed | Stop on mismatch; do not click lifecycle/candidate/mailbox actions under read-only acceptance | **Yes: browser acceptance** |
| 12. Evidence/docs | Record actual commands/exits, artifact digests, schema, statuses and excluded cases | Azure-only results distinguish observed/operator/historical evidence | No overall closure until outstanding scope decisions resolved | Documentation authorized with execution phase |
| 13. Existing resources | Review actual post-validation state and cost; request intended disposition | Retained artifacts/history and operator-selected availability | No automatic shutdown, deletion, resize or AWS operations | **Yes for any resource disposition mutation** |

Local artifact preparation may be completed before entering the migration window to reduce paid runtime and downtime, but registry publication/deployment still require their own approved artifact. Never dispatch the all-in-one workflow as a substitute for these ordered gates.

Later command forms, **not run in 22H**, with reviewed unique values supplied by the operator:

```bash
# Approved backup only; server must already be Ready.
az postgres flexible-server backup create --subscription ECI-Development \
  --resource-group rg-eci-deploy-dev --server-name eci-pg-dev-susanta \
  --name "$ECI_BACKUP_NAME" --only-show-errors
az postgres flexible-server backup list --subscription ECI-Development \
  --resource-group rg-eci-deploy-dev --server-name eci-pg-dev-susanta \
  --query '[].{name:name,completedTime:completedTime,source:source}' -o json

# Only in the guarded migration process with securely injected DATABASE_URL:
python -m alembic upgrade 22b0001

# Later approved local image preparation/publication:
docker build --platform linux/amd64 -t "eci-api:$ECI_RELEASE_TAG" .
az acr login --name eciacrdev6c
docker tag "eci-api:$ECI_RELEASE_TAG" "eciacrdev6c.azurecr.io/eci-api:$ECI_RELEASE_TAG"
docker push "eciacrdev6c.azurecr.io/eci-api:$ECI_RELEASE_TAG"
az acr repository show --name eciacrdev6c --image "eci-api:$ECI_RELEASE_TAG" \
  --query '{digest:digest,name:name}' -o json

# Only after review of registry digest and migration postconditions:
az containerapp update --subscription ECI-Development \
  --resource-group rg-eci-deploy-dev --name eci-api-dev \
  --container-name eci-api-dev \
  --image "eciacrdev6c.azurecr.io/eci-api@$ECI_RELEASE_DIGEST" \
  --revision-suffix "$ECI_REVISION_SUFFIX" \
  --query '{latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName,state:properties.provisioningState}' -o json
```

For later frontend publication, use the verified installed/cached SWA CLI entry point, not an unpinned auto-install. Run from repository root, with an absolute ECI_RELEASE_DIR selecting only the approved dist, and an independently checked ECI_SWA_CLI path. In a non-tracing subshell, obtain the existing SWA deployment token into `SWA_CLI_DEPLOYMENT_TOKEN` using `az staticwebapp secrets list --subscription ECI-Development --name eci-web-dev --resource-group rg-eci-deploy-dev --query properties.apiKey --output tsv --only-show-errors`; never print it. Then the reviewed command form is:

```bash
node "$ECI_SWA_CLI" deploy "$ECI_RELEASE_DIR" --env production \
  --app-location "$ECI_RELEASE_DIR" --swa-config-location "$ECI_RELEASE_DIR" \
  --api-location "" --data-api-location ""
```

Discard the token environment at subshell exit. No API/functions/data-API deployment, token reset, infrastructure creation or cloud login is part of this command. Confirm that client version supports these options before approval. The exact executable path/digest is a pending execution prerequisite, not an already prepared executable release command.

### Proposed Azure fixture — review only, not created

New creation key: **`phase22-azure-20260929-c2451628-80e0-4b26-a610-f09a81c5d326`**. This is unrelated to the AWS fixture/key. Use only a previously mapped, explicitly selected Azure application identity. No email-based identity lookup or new user.

```json
{
  "creation_key": "phase22-azure-20260929-c2451628-80e0-4b26-a610-f09a81c5d326",
  "kind": "action",
  "title": "SYNTHETIC Azure Phase 22 readiness follow-up c2451628",
  "description": null,
  "due": {"kind": "none"},
  "business_context_id": null,
  "sources": []
}
```

Propose eight POSTs relative to the verified Azure API: create (201/v1); identical replay (200/same v1); status `{expected_version:1,status:in_progress,reopen:false}` (v2); status `{expected_version:2,status:completed,reopen:false}` (v3); status `{expected_version:3,status:open,reopen:true}` (v4); status `{expected_version:4,status:cancelled,reopen:false}` (v5); archive `{expected_version:5}` (v6); restore `{expected_version:6}` (v7). Status/archive/restore use only the create-returned item UUID. The JSON creation body above is exact; the status descriptions specify exact key/value bodies for later review, not an executable script.

Between steps, read only that item's detail/events, validating Location, immutable fields, timestamp equality, distinct event IDs, event metadata, version/ordinal ordering and no additional replay event. Final intended state: cancelled, unarchived, version 7, seven events, zero sources/context, no completed timestamp. Record last verified state and synthetic UUID without tokens/content dumps. A first-create 200 means prior execution and requires reconciliation, not a new run. No deletion or cleanup proposed. Due/date/context/candidate and cross-owner cases remain separate scope decisions/local evidence; this minimal fixture does not certify them live.

Browser acceptance must explicitly record `/me`, listing/detail/events HTTP statuses; normal session reuse/sign-in and correct redirect/logout configuration; owner/Azure presentation; Tracking navigation, deep-link reload and lazy assets; history order; filters/empty state; deliberate GET-only loading/error recovery; no CORS/mixed-content/unexpected redirects; and read-only integration with an operator-selected owned Business Context. If no suitable context/session exists, mark the test unavailable rather than create one. Do not navigate into mailbox pages that fetch message/attachment metadata. Attachment/XLSX regression remains local/historical unless separately authorized. Do not copy browser tokens or reuse the AWS-specific validation script/origin/key.

## 12. Backup and rollback strategy

Current PostgreSQL backup retention is **7 days**, geo-redundant backup disabled; earliest restore date observed `2026-09-23T14:05:14.866129Z`. Seven Automatic/Full backups were returned for September 23–29; latest completion **`2026-09-29T14:05:11.381215Z`**. These are service metadata, not a restore rehearsal. No backup was created in 22H.

Before migration, approve a unique named on-demand backup of **eci-pg-dev-susanta** using the exact create/list commands above; require completion and record a UTC pre-migration restore point within the current retention window. If quota/availability/policy prevents a backup, stop before migration and obtain an explicit recovery decision. Do not add a Backup vault or change retention by implication. [On-demand backup procedure](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/how-to-perform-backups).

**Preferred application recovery:** retain schema `22b0001` and all tracking data; roll back only the API image and/or frontend to preserved Phase 21 artifacts. The migration is additive and local historical compatibility tests support this approach; it remains subject to runtime verification. Old UI lacks Tracking; that is not loss of its database rows. Do not downgrade populated tables to make old UI behavior appear clean.

**Backend:** preserved digest in section 4 is currently readable in ACR. After a failed Phase 22 rollout, a separately authorized API-image-only update to that digest with a new rollback suffix can create a replacement revision while preserving the two-container template. Verify latest-ready, old digest, health/readiness and old UI compatibility. No assumption that old revisions will remain retained. Same-revision restart is available operationally, but is neither an artifact rollback nor an automatic first response.

**Frontend:** redeploy only `.phase22h-readiness-20260929/rollback-frontend/` through the same approved client/token mechanism from repository root; confirm SWA Ready and old index/asset hashes. Rollback manifest SHA-256 **`0c81b021d1ae4086de6915cd85dbcb549f443dd549634548b0b7ae80a6035c59`**. Operator must accept the historical-local static-config byte limitation or provide an exact original export. This is a preserved static release, not a complete SWA platform/environment backup or a guaranteed one-click version switch. Keep old/new artifacts and record uncertain upload state before further writes.

**Disaster recovery:** Azure PostgreSQL PITR creates a **new** server, not an in-place rewind. It can lose post-restore-point writes if cut over; Azure Key Vault mailbox credentials are outside the database snapshot. Reconciliation, new-server cost, networking, credentials and a deliberate ACA database-reference cutover require separate approval. No restored server is proposed for normal rollout. [Backup/restore semantics](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore).

Later emergency command form, only after a named recovery target and restore point are separately approved:

```bash
az postgres flexible-server restore --subscription ECI-Development \
  --resource-group rg-eci-deploy-dev --name "$ECI_RECOVERY_SERVER" \
  --source-server eci-pg-dev-susanta --restore-time "$ECI_PRE_MIGRATION_UTC"
```

Verify recovered schema/data retention through approved metadata/validation, review credentials and firewall without copying unsafe defaults, and approve cutover independently. Keep the original server intact. Do not automatically replace secrets, delete the original, reset data, downgrade or retry after an uncertain migration.

## 13. Blockers, unknowns and operator decisions

| Item | Classification / required disposition |
|---|---|
| Current Azure session/inventory/live schema | Verified; no active access blocker found |
| Source/build/API contracts | Compatible; no known Phase 22-specific source/config change required |
| Backend Phase 22 artifact | Not built/published/verified here; exact source manifest, package validation and registry digest required before rollout |
| Backup/recovery | Existing backups verified by metadata; new pre-migration backup and restoration/cost boundaries require approval; recovery not rehearsed |
| Runtime/migration role separation | Selected connection privilege subset verified; distinct-role ownership/default grants require execution preflight if a different migration identity is used |
| Current API health and scanner readiness | Not probed to avoid waking ACA; later authorized runtime gate, not confirmed failure |
| Entra registration/consent and application session | Config matches prior release and backend; actual external-tenant registration and authenticated Azure Phase 22 browser/API results unverified; operator session required |
| SWA client/tooling | No PATH executable; historical cached client must be verified or separately approved tooling supplied; no automatic dependency install |
| Frontend rollback | Five current public files verified; config bytes from matching historical local artifact need explicit acceptance or exact export |
| Deployment/RBAC | Relevant current assignments found; publishing, backup creation, rollback and policy effects are not proven by trial writes |
| Capacity | Existing 1 GiB API/2 GiB scanner/B1ms DB retained; no live Phase 22 load/cold-start proof; do not resize speculatively |
| Scope/acceptance | Approve Azure-specific synthetic fixture separately; define disposition of excluded due/context/candidate/isolation cases; no implied Phase 22 closure |

AWS 22G remains **INCOMPLETE, not CLOSED**. Its earlier Codex attempt remains BLOCKED before W1, separate from later operator W1–W8 PASS. Outstanding AWS context-to-Tracking integration, loading/read-error observations, complete network/security assertions, post-publication distribution status, hosting-header/TLS disposition and low-level lifecycle/artifact-equivalence gaps remain as recorded. None is transferred to Azure as PASS, resolved by this report or silently removed.

## 14. Final assessment

**READY WITH CONDITIONS** for a separately authorized, sequential Azure development rollout using existing resources. There is no discovered architectural or migration incompatibility requiring new infrastructure. Execution remains held at approval/artifact/backup/browser gates; Azure Phase 22 is neither deployed nor validated. This readiness verdict is not unconditional production/capacity/disaster-recovery certification.

## 15. Exact recommended next operator action

Review this report and issue a **fresh Azure-only execution instruction** naming ECI-Development / rg-eci-deploy-dev, the artifact preparation scope, the backup/recovery decision (including possible paid PITR only as separately approved contingency), migration `21d0001 → 22b0001`, API-image-only rollout, frontend publication and operator-controlled acceptance. Explicitly accept or replace the preserved frontend config baseline and identify the existing SWA client and Entra browser session. Keep the proposed synthetic lifecycle authorization separate.

The **first action in that newly authorized session must be read-only `az account show` and baseline revalidation**, not a migration or deployment. The first recommended cloud mutation, after artifact/baseline review, is the individually approved named on-demand PostgreSQL backup. No additional authorization question or execution is initiated by 22H.

**A fresh Codex session is recommended** for the execution phase, carrying this report, preserved manifests, explicit scope and existing authorized sessions. A new session is not a way to bypass unavailable authentication or permissions and must repeat current-state checks.

## 16. Files changed and operations performed

Created report: **`docs/codex/reports/phase_22h_azure_readiness_report.md`**. Modified pre-existing source/configuration/tests/migrations/reports: **none**. Migration files created/changed/executed: **none**.

Created **32 local assessment files** only under **`.phase22h-readiness-20260929/`**: preservation inventory, typecheck/focused-test/build logs, 12-file Azure candidate and manifest, public static diagnostic copy/manifest, six-file rollback candidate and provenance manifest. Dependency tools may update their normal node_modules caches, excluded from the source inventory. No prior frontend/dist or Phase 21/22 evidence was overwritten. Do not publish the entire assessment folder.

Final non-Git verification: **953 pre-existing files unchanged, zero missing; 13 local report links resolve; whitespace/final-newline/conflict-marker checks PASS; all 12 candidate and six rollback manifest entries match their bytes.** Validation script exited 0.

Performed the read-only Azure metadata/role/registry/database operations enumerated above, public SWA GETs, local inspection/validation and Microsoft documentation reads. The one database credential retrieval used the established approved mechanism solely for read-only schema/privilege verification. No SWA deployment token, mailbox credential, browser bearer or unrelated business records were retrieved. No cloud resource mutation, start/stop/restart/scale, backup creation, migration, SQL write, image build/push, deployment/publication, IAM/Entra change, AWS operation, mailbox/attachment access, AI inference, Send or Git operation occurred.

**Readiness-only task: PASS.** Phase 22H is complete; next-phase execution is not started.

## Closure addendum — 2026-10-02

Phase 22 implementation is committed and pushed to `master`: **`46128f261857cfe041c1caadcc679452d03b0967`** (short **`46128f2`**), subject **`feat: add Phase 22 action and obligation tracking`**. Local inspection on 2026-10-02 found a clean working tree and `HEAD`, `master` and the local `origin/master` reference at that commit. Push completion and **CI PASS** are operator-supplied evidence: GitHub Actions workflow **CI**, branch **master**, event **push**, run **`36846483687`**, observed title “feat: add Phase 22 action and obligation ...”. No remote, CI or cloud checks were repeated for this documentation update.

The 2026-09-29 readiness assessment above remains historical. The following subsequent Azure completion results were supplied by the operator for this closure; they were not independently reproduced here. They supersede the earlier rollout status, without rewriting the original readiness conditions or treating AWS observations as Azure evidence.

### Azure backend and schema — operator-observed PASS

| Checkpoint | Recorded result |
|---|---|
| PostgreSQL migration | `21d0001 → 22b0001` completed; live Alembic revision verified `22b0001` |
| Phase 22 tables | `business_work_items`, `business_work_item_sources`, `business_work_item_events` verified |
| Backend source fingerprint used for Azure build | `d354a4f354da13f3de34649c8cc55fb701c059768b6d68afab7bdf41400a02ba` |
| Backend release tag | `p22-azure-20261001T062423Z-d354a4f354da` |
| ACR/backend immutable digest | `sha256:bf1e17c6b5570527bc86d767c0aa9e176ed4ea97bd147b3104120fbbd9d62157` |
| Container Apps revision | `eci-api-dev--p22-bf1e17c6`; LatestRevision and LatestReadyRevision both matched |
| Runtime state | ProvisioningState `Succeeded`; RunningStatus `Running` |
| Health/readiness | `/health`, `/api/v1/health`, `/api/v1/readiness`: HTTP 200 |
| Application identity | Authenticated GET `/api/v1/me` through real Entra/MSAL flow: HTTP 200 |
| Existing UI | Contexts remained available |

The backend build fingerprint and immutable image digest identify the recorded deployment artifact; the Git SHA above identifies the final source commit. They are distinct identifiers.

### Azure Phase 22K W1–W8 — operator-observed PASS

The controlled synthetic lifecycle covered create, idempotent replay, open → in_progress, in_progress → completed, completed → open with explicit reopen, open → cancelled, archive and restore. No duplicate creation event was observed.

Retained Azure Work Item: **`7acbfa6a-6480-46d3-93b5-a83b661ef184`**. Final state: **cancelled**, **version 7**, **archived = false (restored)**, **exactly seven events**, **zero sources**. This fixture remains retained; no further cleanup or disposition was supplied or performed in this closure. This Azure fixture is separate from the AWS fixture recorded in the [AWS report](phase_22g_report.md).

### Azure frontend and browser — operator-observed PASS

| Checkpoint | Recorded result |
|---|---|
| Existing Static Web App | [Azure frontend](https://witty-island-03f5de51e.7.azurestaticapps.net) published successfully |
| SWA production/default environment | `Ready` |
| Approved candidate | `.phase22h-readiness-20260929/dist/` |
| Candidate manifest SHA-256 | `7bf7e64315af98fc2a24bdf017876326d0ed83687847446ec6083d29f68e750e` |
| Verified live index.html SHA-256 | `43bcfc3f1e827356a442addb198a45458a9448b09a08bdcdbc969d0080a0fd55` |
| Verified live main JS bundle | `index-v2r-gI2A.js` |

Browser acceptance passed: Tracking navigation, synthetic Work Item detail, cancelled/version-7/unarchived state, exactly seven lifecycle events, direct detail reload, Tracking filtering and continued Contexts loading. Authenticated Tracking/detail/events/Contexts requests and CORS preflights returned HTTP 200. No blocking CORS, mixed-content, authentication or redirect errors were observed.

### Evidence boundaries and retained artifacts

Local validation remains the historical [Phase 22F results](phase_22f_report.md) and this report's readiness checks. [AWS operator-observed validation](phase_22g_report.md) remains separate from the Azure observations above and from the operator-supplied CI result. No test counts are added together or presented as newly executed.

The ignored `.phase22g-frontend-readiness-20260929/` and `.phase22h-readiness-20260929/` directories remain local deployment/rollback evidence, not source-controlled runtime content. Their contents and rollback artifacts are unchanged by this task.

Mailbox attachment regression was not revalidated in this closure. Production-scale load/recovery was not tested; PITR was not rehearsed; full disaster recovery was not tested. Earlier readiness, backup/restore, capacity and scoped acceptance limitations remain historical evidence; successful rollout does not establish untested recovery or broader acceptance. No unconditional production-readiness or exhaustive Phase 22G closure claim is made.

This closure update changes documentation only. No cloud commands, resources, application source, migrations, fixture state or ignored artifacts were changed; no application suites, deployment, commit or push were run. No later phase was started.
