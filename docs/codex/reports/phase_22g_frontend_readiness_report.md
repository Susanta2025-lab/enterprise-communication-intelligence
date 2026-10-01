# Phase 22G — AWS Frontend Deployment Readiness Assessment

Assessment date: **2026-09-29**. Scope: assessment, local validation and authorized read-only inspection only.

## 1. Executive assessment

**READY WITH CONDITIONS.** The current frontend builds for AWS, passes all local frontend tests and integrates the Phase 22 tracking contracts. The existing SPA distribution, S3 origin, public Phase 21 release and API CORS preflight were independently inspected. No application change, backend rebuild, migration or infrastructure change is identified as necessary for this frontend release.

**Deployment remains on hold** until the operator confirms existing upload/invalidation and rollback permissions, accepts or completes the preserved rollback baseline, and explicitly authorizes the exact frontend write set below. Read-only success does not prove write permissions. This assessment is neither deployment authorization nor a frontend deployment PASS.

| Milestone | Status and evidence boundary |
|---|---|
| AWS backend `eci-api-dev:14`, rollout COMPLETED, database `22b0001` | Established operator baseline; not re-queried or changed here |
| AWS backend authenticated listing, Candidates and W1–W8 | PASS, operator-observed evidence in [Phase 22G report](phase_22g_report.md) |
| Earlier Codex lifecycle attempt | Historically BLOCKED before W1; preserved unchanged |
| Current frontend implementation and local AWS artifact | PASS for this assessment's local checks |
| Existing AWS frontend hosting and public static baseline | Read-only checks passed, with permission-limited gaps below |
| Phase 22 AWS frontend deployment/browser acceptance | **NOT STARTED / NOT RUN** |
| Azure Phase 22 | **NOT STARTED** |
| Overall Phase 22G rollout | **INCOMPLETE; not CLOSED** |

## 2. Scope and inspected evidence

Read the root `AGENTS.md`, [22F report](phase_22f_report.md), complete [22G report](phase_22g_report.md), [AWS runbook](../../../deployment/aws/README.md), [deployment documentation](../../cloud/deployment.md), Phase 21G completion evidence and the Phase 20/16 deployment history. Applied [ADR-030](../../decisions/ADR-030-action-deadline-and-obligation-tracking.md), [ADR-025](../../decisions/ADR-025-browser-frontend-and-authentication-architecture.md) and [ADR-026](../../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md). Earlier architecture/runbook revision numbers are historical and do not supersede the supplied Phase 22 baseline.

Inspected frontend package/lockfile, Vite/TypeScript configuration, effective AWS environment, application composition/routes/navigation, MSAL configuration/provider, `/me` role presentation, API client/types, Tracking hooks/pages/components, candidate integration, Business Context integration, attachment/XLSX rendering and relevant tests. Compared tracking requests/responses against `app/api/routes/work_items.py`, `app/schemas/work_items.py` and local CORS configuration in `app/main.py`.

Evidence categories used throughout:

- **Historical/operator:** existing backend deployment, database revision, authenticated application results and W1–W8. No independent database verification is claimed.
- **Independent local:** source/configuration inspection, tests, AWS build, artifact hashes and preservation inventory.
- **Independent live, read-only:** refreshed AWS identity, selected S3/CloudFront configuration, public static GETs and one unauthenticated API OPTIONS preflight.
- **Not performed:** browser sign-in/interactive testing, authenticated application GETs, deployment writes, IAM changes, backend operations and database access.

No Git command was used. Current branch, HEAD and tracked/untracked state were not independently assessed. The operator's intentionally uncommitted Phase 22 source and existing `AGENTS.md` were preserved. A pre-validation SHA-256 inventory covered 925 existing repository files, including the existing `frontend/dist`, excluding dependency/cache directories and Git internals.

## 3. Current frontend implementation assessment

| Area | Actual implementation and assessment |
|---|---|
| Navigation/routes | `AppShell.tsx` exposes **Tracking** for `communications:analyze`. `App.tsx` registers `/tracking` and `/tracking/:itemId`, with lazy route loading, Suspense and the existing error boundary. The product label is Tracking, not Work Items. |
| Listing | `WorkItemsListPage.tsx` supports server-side kind/status/archive/context/unassociated/due/overdue filters, sort and pagination. Default archive filter is active, meaning **unarchived**, not status=open; the cancelled/restored fixture is eligible. |
| Detail/history | `WorkItemDetailPage.tsx` reads owned detail, then ordered history with limit 20 and offset pagination. Renders status, archive state, manual/confirmed origin, due, version, sources and human-readable history. Seven fixture events fit on the first page. |
| Lifecycle | Versioned status changes, explicit reopen, archive and restore are implemented behind confirmation. Terminal items cannot edit business fields; archived items expose restore. The final fixture should show cancelled, Unarchived, version 7, with Reopen/Archive controls; controls must not be activated during smoke testing. |
| Manual create/edit | `WorkForm.tsx` supports kind, reviewed fields, optional context and explicit none/date/datetime due modes with timezone confirmation and repeated-time selection. These controls were assessed locally only. |
| Candidate integration | `CandidatePanel` is connected to persisted message and attachment analyses, including the shared XLSX attachment result panel. Candidate reads are enabled only when opened. Selection alone creates nothing; confirmation is explicit. Amounts are not paired into tasks. |
| Business Context | Context workspace has a Tracking tab using the same filtered list; existing timeline rendering remains integrated. Work Item ownership is not inherited from communication membership. |
| Loading/empty/error states | Accessible loading statuses, empty lists, safe 401/403/404/409/422 messages, reload/review actions and route-load error handling exist. No-match filters provide a safe empty-state smoke path. |
| Identity/cache | Identity-keyed application tree owns a fresh QueryClient and memory-only creation recovery map. Tracking query keys include identity; requests abort and late callbacks are guarded. Query/mutation retries and focus refetch are disabled. |
| Recovery | Uncertain creation retains the original key/body in memory. Refresh/sign-out clears this recovery; the UI explicitly advises inspecting Tracking before a new creation. Stale versions require reload/review. No automatic lifecycle retry was added. |

No missing Phase 22 route, integration or incompatible local API shape was found. Limits: the detail UI does not separately render `completed_at`/`cancelled_at` or event ordinal/raw metadata; those acceptance fields require read-only network-response inspection if needed. A restored item displays **Unarchived**, with restoration represented in event history. There is no wildcard unknown-route page, so smoke tests must use registered routes. TypeScript response types do not constitute runtime schema validation; live browser evidence is still required.

## 4. Backend/frontend API compatibility

| Frontend use | Local backend contract | Finding |
|---|---|---|
| GET `/api/v1/work-items` | `{items,limit,offset}`; matching typed filters, archive values and sort | Compatible |
| GET `/{id}` and `/{id}/events` | Detail adds sources; events contain type/time/version/ordinal/context/metadata; limit 20 is within max 100 | Compatible |
| POST root | Manual fields plus creation key; sources default empty; 201 or replay 200 | Compatible; frontend uses returned item ID |
| PATCH `/{id}` | Editable fields and positive `expected_version` | Compatible |
| POST `/{id}/status` | `expected_version`, status, explicit reopen flag | Compatible |
| POST `/{id}/archive`, `/{id}/restore` | `expected_version` | Compatible |
| GET `/candidates`, POST `/from-analysis` | Source locator/pagination; explicit `confirmed:true` and reviewed fields | Compatible |
| Conflicts/ownership | Safe errors; owned relative `Location` for existing candidate item | Client allowlists relative UUID links; no foreign-origin navigation |

All tracking operations require authenticated analyze on the server; mailbox-backed creation additionally requires read. UI permission checks are presentation controls, not authorization. The supplied live W1–W8 result supports the deployed lifecycle subset; local inspection/tests support the broader contract. This assessment does not prove byte-for-byte equivalence of the deployed backend and local source or repeat mutation coverage live.

## 5. Authentication and environment configuration

`build:aws` is exactly `tsc -b && vite build --mode aws`. `vite.config.ts` uses React/Tailwind and does not override base path, asset directory, source maps or output directory. The resulting root-relative `/assets/` paths fit the root S3 origin. `BrowserRouter` requires the verified CloudFront fallback; the Azure `staticwebapp.config.json` is just a static object on S3 and does not configure AWS routing or security headers.

Effective AWS configuration was loaded with Vite and validated through the actual `loadFrontendConfig` implementation in memory, without changing source or printing identifiers/secrets:

| Setting | Observation |
|---|---|
| API | `https://dnookm0ucbhv1.cloudfront.net` |
| SPA redirect/logout | `https://d1ut7j94w7lt3b.cloudfront.net` |
| Authority | HTTPS `eciexternaliddev.ciamlogin.com`, tenant path present; known authority derived from that host |
| SPA client | Valid configured public-client UUID; value not reproduced |
| Delegated scopes | Exactly `communications:read`, `communications:analyze`, `communications:connect`, `communications:workflow`, `communications:send`, with one shared API resource prefix; no `.default` |
| Presentation | AWS / `amazon_bedrock` / `eu-south-2`; never an authorization input |
| Environment files | `.env`, `.env.aws`, `.env.aws.local` present; no `.env.local`; no inherited `VITE_*` overrides or unexpected exposed keys |

The API origin, SPA client ID, authority, redirect URI and complete configured scope string were found unchanged in both the currently public Phase 21 bundle and the new AWS bundle. This is independent static compatibility evidence, not a fresh Entra registration/consent query. Historical ADR-026/Phase 16 evidence records the AWS redirect registration; actual sign-in remains a browser acceptance gate.

MSAL remains the public client, with sessionStorage authentication cache, active-account promotion, redirect completion owned by `MsalProvider`, silent token acquisition and safe diagnostics. No frontend secret is required. Existing local AWS auth/API settings are needed to reproduce this build elsewhere; `.env.aws` alone supplies presentation metadata. No dependency installation, new credential, local server, backend rebuild or infrastructure change was required for this build.

The API client uses the configured HTTPS API origin and ephemeral bearer header, with no application cookie mechanism. It uses standard fetch redirect behavior rather than the stricter proposed lifecycle-validator wrapper; no redirect-policy change was made. `/me` is server-authoritative for owner presentation. Existing owner status never bypasses individual object ownership.

## 6. Local validation results and exact artifact

Environment: Node **v24.18.0**, npm **12.1.0**, Vite **8.2.2**, TypeScript **6.0.3**, Vitest **4.1.11**. Existing dependencies were reused. `npm ls --depth=0` in `frontend/` found no dependency errors; 278 installed package versions checked against lockfile v3 had zero mismatches. This is not a fresh registry vulnerability audit or verification of every optional platform package. An initial root-level npm listing was empty and is not used as frontend dependency evidence.

| Check, executed from `frontend/` unless stated | Actual result |
|---|---|
| `npm run lint` | PASS, exit 0 |
| `npm run typecheck` | PASS, exit 0 |
| `npm test -- --run src/test/workItems.test.tsx src/test/workItemDue.test.ts` | **60 passed**, 2 files, 12.35 s, exit 0 |
| `npm test -- --run` | **429 passed**, 32 files, 30.18 s, exit 0; no failures/skips reported |
| `npm run build:aws -- --outDir ../.phase22g-frontend-readiness-20260929/dist` | PASS, exit 0; 344 modules; Vite build stage 1.40 s |
| Effective AWS config parser and old/new bundle setting comparison | PASS |
| HTML and literal chunk-reference resolution; Tracking chunks/API/routes | PASS |
| Output source-map/dotenv checks and private-key/AWS-key marker scan | PASS; limited marker scan, not a universal secret audit |
| Existing-file preservation inventory | PASS; no inventoried pre-existing file changed |

Focused and full tests overlap; do not add them into a 489-test claim. Historical 22F's 60/429 frontend results remain applicable supporting evidence and are now corroborated by fresh runs. Its backend/PostgreSQL results were not rerun. The historical generic production build is distinct from this fresh AWS-mode build.

The new, initially absent output directory preserves the existing `frontend/dist`. Vite warned that an out-of-root output directory would not be emptied; no emptying override was used. The retained main-chunk warning is non-failing: **512.95 kB / 141.56 kB gzip**, above the 500 kB advisory threshold. Initial login shells also emitted a pyenv rehash permission warning; frontend validations exited successfully, and later commands used a non-login shell.

Candidate release directory: `.phase22g-frontend-readiness-20260929/dist/` (12 files). Complete path/size/SHA-256 manifest: `.phase22g-frontend-readiness-20260929/artifact-manifest.json`, SHA-256 `4b684dfbf2d630ec6a2adb045a275737257a75a36bf32c60aafbd650cee099ac`.

| Artifact | SHA-256 |
|---|---|
| `index.html` | `0dbb410f916fb0d0d9277ac5313a49099bef4b2ae6607faa89e07b4822a44a86` |
| `assets/index-dYbR60Oz.js` | `dbb3a46b3305d01ee90e1fb2c678eab032fcfe39735c814b0a00697ed3b9cf9f` |
| `assets/WorkItemsListPage-BnPbMiyz.js` | `01eecc52ae091357873081d8d77b71600b3bea8c2c5f4835aa54e1e8e6486e3b` |
| `assets/WorkItemDetailPage-BIYaHGaG.js` | `c216c92f24a807a6dcbb70c93ced4385d94aaa442d098a17d97493dfca7a5aec` |

The manifest also identifies Context, Mailbox, WorkForm, shared permissions, CSS and three public static files. No artifact was uploaded. Release identity is these bytes and hashes, not a Git commit containing the intentionally uncommitted source.

## 7. AWS S3/CloudFront read-only findings

All AWS CLI calls explicitly used **`--profile eci-dev --region eu-south-2`**. The first sandbox STS attempt could not reach the sign-in endpoint; approved network escalation revealed an expired session. The operator then supplied refreshed identity evidence. A subsequent independent STS check succeeded for account `034456343525`, deployment user `eci-developer`. Codex did not run login, extract cached credentials or rotate credentials. The initial expiry is historical within this assessment, not the final blocker.

| Check | Independently observed result |
|---|---|
| SPA distribution | `E1XFNK98P7PU2W`, enabled, **Deployed**, expected hostname, zero in-progress invalidations; config ETag `E23ZP02F085DFQ` |
| Origin | `eci-web-aws-dev-034456343525.s3.eu-south-2.amazonaws.com`, empty origin path, S3 origin, default root `index.html` |
| Origin protection | OAC `EKFJWGHLO2THQ` / `eci-spa-oac-dev`, SigV4, signing always; bucket policy grants CloudFront GetObject conditioned on this exact distribution ARN |
| Public access | All four bucket Block Public Access settings true |
| Behavior | One default behavior; GET/HEAD only; redirect HTTP to HTTPS; compression enabled; no additional behaviors, edge functions or Lambda associations |
| SPA fallback | Both 403 and 404 map to `/index.html`, response 200, error minimum TTL 0 |
| Cache | Policy ID `658327ea-f89d-4fab-a63d-7e88639e58f6`; direct policy read denied; managed-policy meaning established separately below |
| Inventory | 25 listed frontend objects: 21 retained hashed assets and four root static files; no Phase 22 Tracking chunks in this inventory |
| Current entry | S3 listing: 462-byte `index.html`, last modified `2026-09-23T07:05:47+00:00`, ETag `2bb17bc71ca23f534edd63291a6a6533`; public index matches that ETag |
| Current release | Public HTML references `index-BsxIj7rg.js` and `index-CQm-ji_O.css`, consistent with historical Phase 21G; old bundle lacks `/api/v1/work-items` |
| Public availability/fallback | GET `/`, `/tracking` and `/tracking/64eacb70-c76d-4da4-b0aa-df7908cf686f`: HTTP 200, same 462-byte HTML hash. This proves shell fallback, not Phase 22 React rendering. |
| Public asset reads | Current JS/CSS and three shared static files returned 200 with expected MIME types |
| API CORS preflight | Unauthenticated OPTIONS `/api/v1/work-items`, requesting GET with authorization/x-request-id: 200; exact SPA allow-origin, required headers/methods allowed, no allow-credentials header, max age 600 |

Public current HTML SHA-256: `0e54cf5a82e2a083f64b4abb4be0f7b51a1343cd1fcd77818c1e9b6fc88a2ff3`. Current JS: `87e81cff03334f2f28c376aec4740e76769ccd00719140277ef2c395505c6658`. Current CSS: `54ef1d552590fd1ade2a5f497529eb6c08a6510015aa61d142aa98e7dd95d8af`.

The public entry uses `Cache-Control: no-cache, no-store, must-revalidate`; current JS/CSS responses had no Cache-Control header. AWS identifies the configured managed policy as **CachingOptimized**, with minimum/default/maximum TTLs of 1 / 86,400 / 31,536,000 seconds and no query-string cache key. A positive minimum can override no-cache/no-store for that interval. This policy interpretation comes from [AWS managed cache-policy documentation](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html), not a successful account-level GetCachePolicy call. Do not rely on query-string cache busting; include explicit invalidation and hash verification in deployment.

`X-Cache: Error from cloudfront` on deep-link HTML is consistent with the configured error fallback and HTTP 200, not itself a broken React route. Because fallback also applies to missing asset paths, a 200 alone is insufficient: verify JS/CSS MIME and hashes to catch HTML masquerading as a missing chunk.

Permission-limited observations:

- `HeadObject index.html`: 403 Forbidden. `GetObject index.html`: AccessDenied. Direct S3 backup did not succeed; the local `current-frontend/manifest.json` is empty.
- `GetBucketVersioning`, `GetBucketEncryption`, `GetBucketWebsite`, `GetBucketPolicyStatus`, `GetCachePolicy`, `ListUserPolicies` and `ListAttachedUserPolicies`: AccessDenied. Versioning/encryption settings and identity policy grants remain unverified. The verified regional S3 REST origin does not use website hosting; the separate website-setting API was unavailable.
- No permission test used a write. Current `s3:PutObject`, `cloudfront:CreateInvalidation` and invalidation-status/rollback permissions are **not proven**. Historical successful deployments do not prove current grants. No IAM expansion is proposed.

Six public static files were preserved under `.phase22g-frontend-readiness-20260929/public-current-frontend/`, with a manifest of response MIME/cache headers, ETags, lengths and SHA-256 values. HTML references resolve to the captured JS/CSS/favicon; no additional literal JS chunk references were found in the old bundle. This is a public-byte rollback baseline, **not an S3 versioned export**: source encryption/custom metadata/version IDs were not available. The public favicon, logo and Azure config are byte-identical to the candidate build and need no upload.

Security configuration observations: no response-headers policy appears in the returned default behavior. Sampled public responses lacked CSP, X-Frame-Options, nosniff and Referrer-Policy headers despite those being present in the Azure-only static config. The distribution reports its default CloudFront certificate and `MinimumProtocolVersion: TLSv1`; no TLS-version negotiation audit was performed. These are existing hosting-hardening findings, not source changes or proof of a new Phase 22 regression. Record operator acceptance for this development release or commission separately authorized hardening; do not silently change the distribution.

## 8. Proposed deployment procedure — NOT EXECUTED

**Authorization boundary:** this section is a proposal only. Local validation and read-only inspections above are complete. Every S3 upload, index replacement and invalidation below needs a separate explicit operator deployment instruction after the conditions in section 12 are resolved. No backend, schema, Entra or infrastructure update is included.

1. **Revalidate the target and release.** Confirm profile/account, distribution status/origin/config ETag, current index ETag/hash and absence of another deployment. Recheck source/artifact manifests without Git. If anything differs, stop and reassess; do not reuse a stale approval. Reuse this validated candidate, or build into a new empty local directory with `npm run build:aws -- --outDir <new-directory>` and record/review its new manifest. Never overwrite this artifact or existing `frontend/dist` to repackage it silently.
2. **Complete rollback readiness before the first write.** Recheck the public baseline and retain its six files plus manifests outside the upload tree. Through the operator's existing authorized access, confirm any required S3 index encryption/metadata and ability to restore it. Versioning is unknown: assume no recoverable previous version until verified. Accept the public-byte baseline explicitly or obtain an exact S3 export through existing operator access. Confirm upload and invalidation/status permissions without a trial write or IAM broadening.
3. **Approve a bounded write set.** Eight new content-hashed files under `assets/`, then one replacement of `index.html`, then one SPA invalidation. Leave all 25 existing objects, except the explicitly replaced entry, intact. The three unchanged root files are skipped. Do not upload `.env*`, source, logs, manifests, backups or the whole assessment directory.
4. **Upload assets first.** For each exact file below, ensure a same-name remote object is absent or has identical approved bytes; an unexpected collision stops the operation. Upload the eight assets with `Cache-Control: public,max-age=31536000,immutable`, correct MIME, no public ACL and the established bucket encryption behavior. Do not replace the entry until all assets are independently retrievable with matching hashes/MIME from the SPA host. Read-only public validation is available even though direct object reads were denied.
5. **Publish the entry last.** Under a single-operator deployment window, immediately recheck the old index ETag/hash. Upload only the approved 544-byte `index.html`, `Content-Type: text/html`, `Cache-Control: no-cache, no-store, must-revalidate`, retaining any operator-confirmed required object metadata/encryption. This switches subsequent page loads to the new asset graph; existing tabs can still fetch the old retained assets.
6. **Invalidate only the SPA distribution.** Propose one `/*` invalidation on `E1XFNK98P7PU2W`, covering the entry, root and cached deep-link fallback copies. It evicts caches, not S3 objects; it may cause temporary cache misses/request cost. Record the returned invalidation ID and wait/read its status until Completed before acceptance. Do not invalidate or reconfigure the API distribution.
7. **Stabilize and verify.** Confirm distribution Deployed, invalidation Completed, entry SHA-256 equals the approved value, all eight asset hashes/MIME match, and direct deep links return the new entry. Then perform the operator-controlled browser checklist below. Preserve old and new assets and the rollback folder through acceptance; any later retention cleanup requires separate approval.

Exact candidate asset keys:

```text
assets/index-dYbR60Oz.js
assets/index-Gheok34O.css
assets/permissions-CAx5a8kf.js
assets/WorkItemsListPage-BnPbMiyz.js
assets/WorkItemDetailPage-BIYaHGaG.js
assets/WorkForm-CoxQFf2V.js
assets/ContextWorkspacePage-MZDC2C5y.js
assets/MailboxWorkspacePage-EuPBlbHK.js
```

Command forms for the later authorized operator, **not executed here**; run from repository root, set `RELEASE_DIR` to the approved candidate directory, and use each exact allowlisted key rather than an unrestricted recursive upload:

```bash
# Per approved .js asset; for the one CSS file use text/css.
aws s3 cp "${RELEASE_DIR}/${ASSET_KEY}" \
  "s3://eci-web-aws-dev-034456343525/${ASSET_KEY}" \
  --content-type text/javascript --cache-control 'public,max-age=31536000,immutable' \
  --profile eci-dev --region eu-south-2 --only-show-errors

# Only after every asset passes verification and index metadata is confirmed.
aws s3 cp "${RELEASE_DIR}/index.html" \
  s3://eci-web-aws-dev-034456343525/index.html \
  --content-type text/html --cache-control 'no-cache, no-store, must-revalidate' \
  --profile eci-dev --region eu-south-2 --only-show-errors

aws cloudfront create-invalidation --distribution-id E1XFNK98P7PU2W \
  --paths '/*' --profile eci-dev --region eu-south-2
aws cloudfront get-invalidation --distribution-id E1XFNK98P7PU2W \
  --id "${INVALIDATION_ID}" --profile eci-dev --region eu-south-2
```

Do not use `aws s3 sync --delete`. The historical Phase 20 run uploaded new assets but deletion was denied, retaining older releases. If allowed, that flag would delete destination objects absent from the local build, including previous chunks needed by open tabs, rollback assets or unrelated objects. This proposal has no delete permission requirement and no destructive synchronization. Even a later cleanup needs its own reviewed key list and explicit authorization.

## 9. Rollback and recovery — proposed, NOT EXECUTED

Obtain explicit contingency rollback authorization with the later deployment instruction; otherwise stop and present the observed failure before any restoration write. Define triggers as missing/mismatched assets, incorrect environment, broken sign-in/CORS, unrecoverable route errors or failed owned-fixture reads attributable to the frontend.

- **Before index publication:** stop on upload/verification failure. Existing entry remains authoritative. Leave any new unused hashed files in place; do not clean them up automatically.
- **Ambiguous index upload:** inspect the public index, S3 listing/metadata where permitted and hashes before retrying. Determine whether old or new bytes are serving; do not infer failure from a timeout alone.
- **After publication:** verify retained previous JS/CSS/static files against the preserved manifest. If intact, restore only the captured old `index.html` to the same key with its recorded HTML/cache settings and operator-confirmed required metadata/encryption. If an old asset is missing, restoration of that exact captured asset needs inclusion in the rollback authorization and must precede the entry restoration.
- Invalidate `/*` on the same SPA distribution, record the ID, confirm Completed, then verify the previous entry/asset hashes and existing sign-in/read-only behavior. Keep new assets too; no deletion is needed.
- If invalidation fails or a client keeps a cached entry, report the partial state and inspect before retrying. Do not repeatedly upload unchanged bytes or clear browser auth storage to force success. Controlled browser reload follows cache stabilization.

The old public index is 462 bytes, SHA-256 `0e54cf5a82e2a083f64b4abb4be0f7b51a1343cd1fcd77818c1e9b6fc88a2ff3`. Its captured response cache setting is `no-cache, no-store, must-revalidate`. Full original S3 metadata is not yet verified; resolve that condition before relying on exact restoration.

**Frontend rollback does not roll back ECS task definition 14, database revision `22b0001`, Work Items or their audit history.** The previous UI would simply lack Tracking. Do not downgrade schema, rerun migrations, remove the synthetic item, change backend capacity or deploy the old backend as a frontend recovery action.

## 10. Operator-controlled browser acceptance checklist — NOT RUN

Use the existing authorized Microsoft Entra application identity/Platform Owner session. Fixture: `64eacb70-c76d-4da4-b0aa-df7908cf686f`, creation key `phase22g-20260928-3d55c464-c7cf-4752-b45f-6bc5d9885a65`. Only read the existing fixture; do not create or mutate anything.

- [ ] Open the SPA HTTPS origin and registered Tracking deep link; confirm new entry and lazy chunks load, including after a controlled reload. Check MIME as well as HTTP status.
- [ ] Existing MSAL session resumes or the operator completes normal Entra sign-in; redirect returns to the same SPA. No credential extraction, alternate identity or auth-setting change.
- [ ] Authenticated `/api/v1/me` is 200 and the existing expected owner presentation is derived from its response. Retain only status and role outcome, not raw identity data. Owner status must not substitute for fixture ownership.
- [ ] Tracking navigation appears and `/tracking` renders. Listing returns 200; use cancelled status, active/unarchived visibility and no context restriction to find the known fixture. Paginate if needed; do not retain unrelated row contents.
- [ ] Open the fixture detail directly. Confirm original UUID, manual origin, cancelled, Unarchived, version 7, no context and zero sources. Read-only response inspection may confirm cancellation timestamp present and completion timestamp absent; the page does not render those timestamps separately.
- [ ] History shows created, four status changes, archived and restored in versions 1–7. Final event is restored, ordinal 0, metadata `{}`. If confirming the empty tail, use an authenticated read-only history GET with `limit=100&offset=7`; do not rerun W1–W8. No browser token copying.
- [ ] Observe loading using browser throttling limited to GETs; use no-match filters for empty state. Test recoverable read errors by temporarily blocking only a Tracking GET in DevTools, then unblock/reload. Keep sign-in/network tools intact; do not manufacture a real unauthorized write or invalid transition.
- [ ] No CORS, mixed-content, unexpected redirect, authentication or chunk errors in the browser console/network summary. After a 401, stop and refresh the existing session through normal UI before retrying reads. Do not export HARs, raw responses, headers or token claims.
- [ ] Existing Business Context navigation/list/Tracking integration remains usable with operator-selected authorized records and read-only actions; no context creation, suggestion, association or mutation. Avoid recording unrelated business content.
- [ ] Confirm attachment/XLSX rendering compatibility through the passing local regression evidence and, only if already displayed in the session without new mailbox/attachment requests, existing saved UI. **Do not navigate to a mailbox workspace that automatically fetches messages/attachment metadata.** Live mailbox/attachment workflows are outside this smoke scope; no Analyze, retrieval, candidate confirmation, AI request or email action. Mark unavailable live coverage NOT RUN rather than expanding authorization.

Reopen, Archive, Restore, Create, Edit, candidate confirmation and workflow buttons are not part of this browser smoke. Stop on a mismatch, preserve a sanitized status/hash/error-category record and apply only separately authorized recovery. No second identity or live cross-owner test is authorized.

## 11. Security and privacy considerations

Preserve separation of application, mailbox, workload, database and deployment identities. Authoritative authorization remains verified `(iss, sub)` → internal user → application role plus object ownership. MSAL cache behavior and existing scopes are unchanged; the presence of a Send scope does not authorize sending during this task. AI remains advisory and human confirmation remains explicit.

No bearer token, cookie, token claim, secret value, provider response, raw attachment content or unrelated record was read into this report. Effective environment checks printed only public origins, authority hostname, permission names and validation booleans. Public SPA files inherently contain public client configuration; they are not backend credentials. Local manifests contain file hashes and sanitized static response metadata only. Do not publish diagnostic/source-inventory files to S3.

No backend hardening was weakened, no ECS Exec enabled and no access denial bypassed by IAM edits. The authenticated AWS CLI's denied S3 read was recorded; the separately authorized public CloudFront GETs retrieved only publicly served static application assets. No cloud identity was used as an application user credential.

## 12. Explicit blockers, conditions and outstanding decisions

| Condition | Required resolution before deployment |
|---|---|
| Current upload/invalidation/rollback permissions not proven; IAM inspection denied | Operator confirms existing `s3:PutObject` on the exact release keys/index and `cloudfront:CreateInvalidation`/`GetInvalidation` on the SPA distribution, including rollback writes. Do not request delete or broad IAM grants. |
| Direct S3 backup/head and versioning/encryption inspection denied | Operator accepts the public-byte backup with known limits or supplies an exact export using existing access; confirm required index metadata/encryption and retain a usable rollback copy. No assumption of bucket versioning. |
| No authenticated Phase 22 frontend browser proof yet | Reserve the same authorized operator session and run section 10 only after an explicitly authorized upload and stabilization. |
| Existing hosting security-header/TLS configuration limits | Operator accepts the unchanged development posture or separately authorizes assessment/hardening; do not change infrastructure within frontend deployment by implication. |
| Mutable local/uncommitted release and concurrent deploy risk | Approve the exact manifest and recheck artifact/current index immediately before writes; use one operator. A rebuild or changed target requires renewed artifact review. |
| Deployment/rollback authority | Explicitly authorize the nine-object upload set, one SPA invalidation, read-only acceptance and any desired contingency rollback. No approval is inferred from this readiness request. |

No source-level or build blocker was found. S3 reads/IAM introspection are permission blockers for complete independent verification, not proof that uploads are denied. Initial AWS session expiry was resolved. No frontend, backend or Azure deployment was performed.

## 13. Exact recommended next operator action

Review the candidate manifest and preserved public Phase 21 release. Confirm existing upload/invalidation/rollback capabilities and the rollback metadata/encryption decision using established operator access; provide only sanitized confirmation. Then issue a **separate explicit frontend-only deployment authorization** for section 8's eight assets, index replacement and SPA invalidation, including whether section 9 contingency rollback is authorized. Preserve the backend and database as deployed. Do not start with another build or migration merely because this assessment is complete.

A fresh Codex session is **not required and is not recommended solely to fix authentication**; `eci-dev` was successfully revalidated here. Continuing with this report and the exact local manifests preserves useful context. If a fresh session is used for operational clarity, it must reread `AGENTS.md`, both Phase 22G reports and the manifests, recheck current state, and obtain the separate deployment instruction. A fresh Codex session does not confer access to the operator's authenticated browser.

## 14. Files and operations performed

- Created this report only as a project-document change: `docs/codex/reports/phase_22g_frontend_readiness_report.md`. Existing reports, `AGENTS.md`, application/frontend source, lockfile, configuration, browser validation script, migrations and deployment artifacts were preserved.
- Created local assessment evidence under `.phase22g-frontend-readiness-20260929/`: initial file-hash inventory, focused/full test logs, AWS build log, 12-file candidate build and manifest, public-response/CORS summaries, six-file public prior-release copy and manifest, and an empty manifest for the denied direct-S3 backup. These are local validation/preservation artifacts, not deployed releases. TypeScript/Vitest may update their normal dependency-cache files under `frontend/node_modules`; those caches are outside the source preservation inventory.
- Ran dependency/configuration checks, ESLint, type checking, focused/full frontend tests, one AWS-mode build and non-Git artifact/preservation checks. No dependency install, backend tests, database tests or production browser tests were run.
- AWS operations were restricted to STS and the S3/CloudFront/IAM reads enumerated above; denied reads are retained as evidence. Public HTTP operations read the SPA's static files/routes and sent one unauthenticated API OPTIONS request. Consulted public AWS cache-policy documentation.
- **No S3 mutation, CloudFront invalidation, deployment, resource/configuration/IAM change, backend rebuild, database query/write/migration, authenticated lifecycle request, mailbox operation, attachment retrieval, AI inference, Send or Git operation occurred.** No credentials were created/rotated and no existing file was discarded. Azure was not accessed.

Assessment complete. AWS frontend deployment remains NOT STARTED; Phase 22G remains incomplete.

## 15. Post-assessment deployment addendum — 2026-09-29

**AWS Phase 22 frontend deployment and core authenticated browser acceptance: PASS**, based on supplied operator evidence. Sections 1–14 above remain the original pre-deployment readiness assessment, including its historical hold, NOT STARTED / NOT RUN conclusions and unchecked checklist. This addendum records subsequent events; it does not retrospectively turn the assessment into a deployment or mark every checklist item passed. Full results and the current closure assessment are in the [Phase 22G deployment and browser acceptance addendum](phase_22g_report.md#aws-frontend-deployment-and-operator-controlled-browser-acceptance--2026-09-29).

The operator explicitly authorized and manually executed the bounded deployment, with contingency rollback authorization and acceptance of the documented public-byte backup limitations. Target: profile `eci-dev`, account `034456343525`, IAM user `eci-developer`, region `eu-south-2`, bucket `eci-web-aws-dev-034456343525`, SPA distribution `E1XFNK98P7PU2W`, frontend `https://d1ut7j94w7lt3b.cloudfront.net`. The existing `eci-phase16d-spa-publish-temp` policy was inspected and grants bucket `s3:PutObject` and SPA `cloudfront:CreateInvalidation` / `cloudfront:GetInvalidation`; no IAM policy changed.

The operator verified candidate manifest SHA-256 `4b684dfbf2d630ec6a2adb045a275737257a75a36bf32c60aafbd650cee099ac`, uploaded all eight exact section 8 assets, and independently verified all eight public CloudFront SHA-256 and Content-Type checks: **8/8 PASS**. The prior entry SHA-256 `0e54cf5a82e2a083f64b4abb4be0f7b51a1343cd1fcd77818c1e9b6fc88a2ff3` was verified locally and live before replacement. Published Phase 22 entry SHA-256 `0dbb410f916fb0d0d9277ac5313a49099bef4b2ae6607faa89e07b4822a44a86` passed. SPA invalidation `IBTTWV25MGS4CFJDFY0I466T5W`, path `/*`, reached **Completed**. No previous assets were deleted.

The preserved `.phase22g-frontend-readiness-20260929/public-current-frontend/` remains a public-byte rollback baseline, not an exact S3 object/version backup. AccessDenied gaps for original metadata, encryption and bucket versioning remain; operator acceptance of these development limitations does not verify them. No rollback was necessary or executed, and not all rollback operations were independently tested.

Using the existing authorized Entra session, the operator observed PASS for application loading, session reuse, Platform Owner/AWS indicators, Tracking navigation/list/detail, direct detail URL and reload, session persistence, seven ordered audit events, absence of visible JavaScript/CORS/authentication/chunk errors, Business Context listing, empty-state filtering and restoration of the fixture after resetting Status to All statuses. Network-panel GETs for `/api/v1/me`, the fixture detail and its `/events?limit=20&offset=0` each returned **HTTP 200**. Fixture `64eacb70-c76d-4da4-b0aa-df7908cf686f` remained manual, cancelled, Unarchived, version 7, with zero source associations and seven events ending in restored. These are operator-observed browser/API results; screenshots do not independently prove database state. W1–W8 were not repeated and no additional lifecycle writes occurred.

**Overall Phase 22G remains INCOMPLETE, not CLOSED. Azure Phase 22 remains NOT STARTED.** Outstanding original acceptance evidence includes existing-context Tracking integration, deliberately observed loading and induced recoverable read errors, complete network/security assertions, post-publication distribution status, and a separate explicit disposition of the historical hosting security-header/TLS condition. The lifecycle report's original low-level assertion/artifact-equivalence gaps remain. Closure requires evidence or an explicit scope/acceptance decision for remaining in-scope criteria, with a separate Azure rollout disposition. Public-byte rollback acceptance does not resolve unrelated conditions.

Live mailbox/attachment workflows, candidate confirmation, AI inference, additional lifecycle mutations, cross-owner/additional-identity checks and direct SQL verification were not independently exercised during frontend acceptance. These exclusions are not new PASS results or authorization to test them. The earlier Codex attempt remains BLOCKED before W1; the later operator W1–W8 PASS remains separately recorded.

This addendum and the Phase 22G report update are documentation-only, using supplied evidence and local documentation. Codex performed no cloud or HTTP operations, backend/database operations, application/configuration/infrastructure/migration changes, dependency installation, rebuild or Git operations. No application tests were run (0); prior validation counts remain historical. The deployed AWS backend, PostgreSQL database and existing fixture were unchanged by this update.
