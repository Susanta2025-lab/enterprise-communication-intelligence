# Phase 22G — Controlled AWS Work Item Lifecycle Validation

> **2026-10-02 status update:** See the [dated closure addendum](#closure-addendum--2026-10-02). Earlier assessments and limitations below retain their original chronology.

Original assessment date: 2026-09-28. Updated: **2026-09-29**, following operator-executed frontend deployment and browser acceptance. Overall status: **AWS PHASE 22 DEPLOYMENT AND SCOPED FRONTEND/BROWSER ACCEPTANCE PASS; OVERALL PHASE 22G INCOMPLETE, not CLOSED.** Remaining acceptance evidence and Azure rollout are identified in the dated addendum below.

| Execution / deployment scope | Current status |
|---|---|
| Earlier Codex execution | **BLOCKED before W1**; zero lifecycle POST requests |
| Subsequent operator-controlled browser execution | **W1–W8 PASS**, including successful W4 after an HTTP 401 interruption and read-only reconciliation |
| Phase 22G AWS backend lifecycle validation | **PASS**, based on operator-reported authenticated API observations |
| Phase 22 local implementation/validation | **PASS**, historical Phase 22F evidence; not rerun |
| AWS database migration and backend deployment | **PASS**, previously recorded operator evidence: `22b0001`, `eci-api-dev:14` |
| AWS Phase 22 frontend deployment | **PASS**, operator-executed on 2026-09-29 |
| Core authenticated frontend browser acceptance | **PASS**, scoped operator observations on 2026-09-29 |
| Azure Phase 22 | **NOT STARTED** |

The operator approved the procedure below and subsequently executed W1–W8 separately through Chrome DevTools using the existing authenticated Microsoft Entra session. The section “Phase 22G — Operator-Controlled AWS Lifecycle Execution (Actual Results)” records those sanitized observations. The 2026-09-29 addendum records the later operator-executed AWS frontend deployment and browser acceptance. Earlier pending, blocked, not-executed and zero-write statements remain historical evidence for their respective preparation or Codex attempts; they do not describe the subsequent operator executions. The fixed fixture and all eight approved request bodies are unchanged. The complete Phase 22G cloud rollout is **not CLOSED**.

## Original readiness assessment (before execution authorization)

The inspected implementation supports a single source-free manual fixture, owned retrieval, creation replay, versioned status changes, ordered event history, archive and restore. Execution remains conditional on operator approval of the exact write set below, confirmation of the existing authenticated identity, and fresh read-only preflight checks. This report is a procedure and local evidence record, not an AWS lifecycle pass.

| Deployment prerequisite | Evidence available for this assessment | Verification this session |
|---|---|---|
| Region `eu-south-2` | Operator supplied | Not independently queried |
| ECS `eci-api-dev:14`, rollout COMPLETED | Operator supplied | Not independently queried |
| PostgreSQL Alembic `22b0001` | Operator supplied; matching local migration exists | No live database connection |
| CloudFront health/readiness PASS | Operator supplied | No live HTTP request |
| Authenticated Work Items listing PASS | Operator supplied | No live HTTP request |
| Authenticated Candidates retrieval from existing XLSX analysis PASS | Operator supplied | No live HTTP request |

No matching `eci-api-dev:14` deployment artifact was found in the searched repository files. Older cloud documentation describes historical task definitions and retained-resource states; it does not establish current deployment state. Phase 22F explicitly reports local validation. The supplied deployment results are therefore recorded as operator-attested evidence, not independently reproduced evidence. The local/deployed artifact equivalence has not been established in this session.

Repository files and applicable root `AGENTS.md` were inspected directly. No Git commands were used, so branch, HEAD and tracked/untracked status were not assessed. The report did not previously exist. Existing implementation and diagnostic files were preserved.

## Inspected contracts and utilities

- `app/schemas/work_items.py` and `app/api/routes/work_items.py`: strict creation body; no client authority fields; POST creation returns 201 or replay 200 with owned `Location`; detail and event reads; versioned status/archive/restore endpoints.
- `app/domain/models/business_work_item.py`, `business_work_item_event.py`, `work_item_due.py`, `work_item_intent.py`, and `work_item_query.py`: lifecycle rules, timestamp invariants, strict fields, creation-key validation, event metadata and archive filtering.
- `app/application/services/work_items.py` and `identity.py`: verified identity mapping; owner-scoped operations; creation may resolve/create an identity; manual source-free creation has no provider/executor dependency.
- `app/infrastructure/storage/repositories/business_work_item.py`: owned persistence, atomic mutations and events, lifetime creation-key lookup, and event ordering by item version then ordinal then ID.
- `tests/integration/test_work_items.py`: reusable local HTTP fixture with in-memory SQLite, synthetic signed JWT validator, and forbidden AI/scanner/connector/executor dependencies. Existing tests cover replay, privacy, ownership, versions, terminal reopen, archive and restore. These JWT helpers are local-only and must never be used against AWS.
- `tests/conftest.py`: local tests ignore developer dotenv configuration. `.phase22f-local-tests.log` is a guarded disposable PostgreSQL test runner; it was inspected but not executed or repurposed for AWS.
- `frontend/src/auth/tokenProvider.ts` and `frontend/src/api/client.ts`: existing MSAL silent token acquisition and authenticated Work Item client methods. `docs/cloud/authentication.md` documents application OIDC identity separation.

Authorization remains verified `(iss, sub)` → internal user → application role/capability. These endpoints require authenticated `communications:analyze`; this capability name does not cause inference. Email, mailbox identity and Platform Owner status do not replace ownership. Completion/cancellation record tracking declarations only and execute no business action.

## Authentication and read-only preflight after approval

Use the same existing authorized application OIDC identity and mechanism used for the successful AWS reads. The repository browser mechanism is MSAL via `MsalAccessTokenProvider`, using the configured ECI API scopes and active account. Do not create another identity, mint test tokens, change authentication settings, or use AWS workload/deployment credentials as API credentials.

Keep bearer material within the existing authentication/request mechanism. Never print it, put it in command arguments, paste it into the report, export a HAR, capture authorization headers, or persist a request dump. Capture only the sanitized evidence fields specified below. Do not request new permissions if authentication fails; stop.

The documented API base is `https://dnookm0ucbhv1.cloudfront.net` (`docs/cloud/deployment.md`). Confirm that this is the exact endpoint used by the completed deployment validation before sending authenticated requests. No bearer goes to the ALB or task-IP HTTP endpoint. Refuse redirects to another origin. The SPA and API CloudFront hosts are different.

Before W1:

1. Confirm the current deployment evidence still identifies `eu-south-2`, task definition `eci-api-dev:14`, completed rollout, and schema `22b0001`. Use existing sanitized evidence or authorized read-only inspection; do not redeploy, migrate, or repeat a possibly completed operation. Health alone does not prove task revision or schema version.
2. GET `/health` and `/api/v1/readiness`; expect HTTP 200 and healthy/ready status. GET `/api/v1/work-items?limit=1&offset=0`; expect HTTP 200, but do not retain unrelated item contents.
3. Confirm the active account is exactly the previously authorized identity with an existing internal mapping. An empty Work Items list alone is insufficient: unmapped users can receive an empty list. The earlier successful owned Candidates retrieval is supporting evidence only if tied to this same identity. If fresh proof is needed, repeat only the existing approved Candidates GET with its known persisted analysis ID, in memory; retain status/count only. Do not list mailboxes, retrieve bytes, analyze, or create provenance. If no safe identity proof is available, stop before W1.
4. Confirm there is no previous execution of this run. Preserve the fixed creation body and any previously recorded returned item ID. Never generate a replacement creation key to recover an uncertain request.

## Fixed synthetic fixture

Run ID / creation key: `phase22g-20260928-3d55c464-c7cf-4752-b45f-6bc5d9885a65`.

Use this exact JSON body for W1 and W2:

```json
{
  "creation_key": "phase22g-20260928-3d55c464-c7cf-4752-b45f-6bc5d9885a65",
  "kind": "action",
  "title": "SYNTHETIC Phase 22G 3d55c464-c7cf-4752-b45f-6bc5d9885a65",
  "description": null,
  "due": {"kind": "none"},
  "business_context_id": null,
  "sources": []
}
```

No real business content, due date, context, source, candidate, mailbox reference, or confirmation metadata is supplied. Owner, status, version and timestamps are server-authoritative. `{id}` below means only the UUID returned by W1 for this fixture; never substitute another item's ID.

## Exact proposed AWS write operations — approval boundary

All paths below are relative to the confirmed HTTPS API base. Send JSON using the existing authorized OIDC mechanism. Execute sequentially with no background retries and check each result before continuing.

| Step | Method and path | Exact request body | Expected response and database effect |
|---|---|---|---|
| W1 | POST `/api/v1/work-items` | Fixed fixture JSON above | 201; one owned manual item, open, version 1; one `created` event; zero source rows |
| W2 | POST `/api/v1/work-items` | Identical fixed fixture JSON | 200; same ID, Location and current version 1; no additional item, event or source; unchanged timestamps |
| W3 | POST `/api/v1/work-items/{id}/status` | `{"expected_version":1,"status":"in_progress","reopen":false}` | 200; version 2, open → in_progress; one `status_changed` event |
| W4 | POST `/api/v1/work-items/{id}/status` | `{"expected_version":2,"status":"completed","reopen":false}` | 200; version 3, in_progress → completed; server `completed_at` populated; one event |
| W5 | POST `/api/v1/work-items/{id}/status` | `{"expected_version":3,"status":"open","reopen":true}` | 200; version 4, completed → open; `completed_at` cleared; one event |
| W6 | POST `/api/v1/work-items/{id}/status` | `{"expected_version":4,"status":"cancelled","reopen":false}` | 200; version 5, open → cancelled; server `cancelled_at` populated; one event |
| W7 | POST `/api/v1/work-items/{id}/archive` | `{"expected_version":5}` | 200; version 6, cancelled retained; server `archived_at` populated; one `archived` event |
| W8 | POST `/api/v1/work-items/{id}/restore` | `{"expected_version":6}` | 200; version 7, cancelled retained; `archived_at` cleared; one `restored` event |

Total authorized scope proposed: **eight POST requests, seven state-changing transactions, one retained synthetic item and seven events, zero source rows**. No identity rows should be created because an existing mapped identity is a mandatory prerequisite. No direct SQL writes or database cleanup are proposed. Normal application request telemetry may be emitted, but bearer tokens and request content must not be recorded.

The final fixture remains restored, unarchived and cancelled at version 7. Archive is reversible and is not deletion. No additional cleanup/archive call is included in this approval request.

## Read assertions between writes

After W1, GET `/api/v1/work-items/{id}` using the same identity. Expect 200, exact fixture fields, `sources: []`, `business_context_id: null`, `creation_origin: "manual"`, `confirmed_at: null`, `overdue: false`, and version 1. Verify creation `Location` is exactly `/api/v1/work-items/{id}`. `completed_at`, `cancelled_at`, and `archived_at` must initially be null.

After W1 and W2, GET `/api/v1/work-items/{id}/events?limit=100&offset=0`. Both reads must contain the same single created event with identical event ID, version 1 and ordinal 0. Compare creation/replay IDs and timestamps in memory. This demonstrates replay does not append history; it is not a direct SQL row-count audit.

After each of W3–W8, GET the owned detail and event history. Confirm version increments exactly once, the indicated status/timestamps, unchanged synthetic fields/context/sources, and exactly one new event. Stop on any mismatch. After W7, owned detail and history must remain readable despite archive. After W8, status must still be cancelled with the original cancellation timestamp, and `completed_at` must remain null.

Final history must contain exactly these entries, ordered as returned:

| Item version | Event type | Required metadata |
|---|---|---|
| 1 | `created` | `status: open`, `due: {kind: none}`, `creation_origin: manual` |
| 2 | `status_changed` | `old_status: open`, `new_status: in_progress` |
| 3 | `status_changed` | `old_status: in_progress`, `new_status: completed` |
| 4 | `status_changed` | `old_status: completed`, `new_status: open` |
| 5 | `status_changed` | `old_status: open`, `new_status: cancelled` |
| 6 | `archived` | `{}` |
| 7 | `restored` | `{}` |

All seven event IDs must be distinct, `work_item_id` must equal the fixture UUID, `event_ordinal` must be 0, and `context_at_event_id` must be null. Event timestamps must be timezone-aware and correspond to the respective item updates. Responses must omit owner/actor identity fields and historical title/description content. GET events with `limit=100&offset=7` must return an empty list.

## Failure and uncertain-outcome handling

Any unexpected HTTP status, identity change, unexpected item ID/version/event, redirect, or failed precondition stops the sequence. Record only sanitized status/error code and the last verified state. Do not force a new expected version or adjust payloads to make the sequence pass.

On a lost creation response, retain the exact creation key/body. The explicitly proposed W2 replay is the only planned repeat and can recover the current item without another creation. If W1 initially returns 200, the key was already used: reconcile the returned item/history and stop the fresh-run sequence rather than treating it as a new creation. Further retries beyond W1–W8 require review.

On an uncertain status/archive/restore response, GET the known fixture and events before any further write. A successful commit may already have advanced the version. Do not blindly retry or reset the version. Stop and present the reconciled state for an updated procedure. No new fixture, direct SQL repair, hard deletion, or unapproved cleanup is permitted.

## Preparation evidence (before execution authorization)

| Evidence class | Result |
|---|---|
| Current local domain tests | `python -m pytest tests/unit/domain/test_business_work_item.py -q`: **85 passed in 0.36s**, exit 0 |
| Historical Phase 22F local checks | Report records 473 focused backend, 214 PostgreSQL, 3147 full backend, 60 focused frontend and 429 full frontend passing tests; not rerun here |
| Current AWS preflight | NOT RUN in this session |
| AWS W1–W8 and owned/history assertions | NOT RUN — awaiting explicit operator approval |

Local tests validate transition rules, archive/restore, versions and model invariants; they do not exercise CloudFront, deployed OIDC, ECS or RDS. No new backend/frontend implementation or migrations were changed, so full suites, PostgreSQL tests and frontend builds were not rerun. Git-based checks were not run because this task prohibits Git operations.

For each subsequent live step append only: UTC time, step ID, method/path with synthetic item UUID, HTTP status, safe request correlation ID if available, expected/observed item version and status, timestamp presence/equality checks, source count, event count/types/versions, and PASS/FAIL. Record the returned synthetic item UUID once for recovery. Do not save full responses, authorization headers, claims, email addresses, existing analysis contents or unrelated items. Keep proposed expectations separate from observed results.

| Live checkpoint | Observed HTTP/version/events | Result |
|---|---|---|
| Read-only preflight | — | NOT RUN |
| W1 + owned detail/history | — | NOT RUN |
| W2 + replay/history comparison | — | NOT RUN |
| W3 + detail/history | — | NOT RUN |
| W4 + detail/history | — | NOT RUN |
| W5 + detail/history | — | NOT RUN |
| W6 + detail/history | — | NOT RUN |
| W7 + archived detail/history | — | NOT RUN |
| W8 + restored detail/final history | — | NOT RUN |

## Preparation scope and completion record

- Created: `docs/codex/reports/phase_22g_report.md`. Existing source/configuration files modified: none.
- Migration changes: none. No live database queries or migrations executed.
- Cloud resources touched this session: none. No AWS or Azure calls, infrastructure changes, deployments or IAM changes.
- No mailbox operations, attachment retrieval, inference, email sending, unrelated data changes or Git operations.
- Limitations: AWS behavior remains unvalidated by this session. One identity proves successful owned access, not live cross-owner isolation. Negative transitions, conflict races, due dates, contexts, provenance/candidate conversion and external execution are outside this live procedure; relevant existing local tests are not substitutes for live evidence.
- Phase 22G live execution is pending. No later phase has been started.

**Operator approval requested:** approve read-only preflight and exactly W1–W8 for this fixture, leaving one restored/cancelled synthetic item and its seven events. Stop here until approval, as explicitly required by the Phase 22G task, requirement 6.

## Approved execution attempt — actual evidence, 2026-09-28

Authorization received: read-only AWS preflight and exactly W1–W8 for the fixed fixture, without additional writes or cleanup. The complete report and root `AGENTS.md` were read before attempting preflight. No further lifecycle authorization was requested. Sandbox network access required escalation for the approved read-only checks; those checks were then attempted outside the sandbox.

**Outcome: BLOCKED before W1.** Public health checks passed, but independent ECS verification could not complete because the existing AWS CLI session expired. Secure authenticated application access was also unavailable through the tools/session exposed to this agent. No alternative authentication mechanism or login was attempted.

| Preflight checkpoint | Actual sanitized observation | Result |
|---|---|---|
| API destination | Local `frontend/.env.aws.local` configures `VITE_ECI_API_BASE_URL` as `https://dnookm0ucbhv1.cloudfront.net`, matching the approved report. This does not independently identify the deployed frontend artifact. | PASS for configured endpoint match |
| CloudFront liveness | 2026-09-28T11:55:44.298170+00:00: GET `/health`, HTTP 200, `status: healthy`; redirects disabled | PASS |
| CloudFront readiness | 2026-09-28T11:55:44.363388+00:00: GET `/api/v1/readiness`, HTTP 200, `status: ready`; redirects disabled | PASS |
| ECS deployment in `eu-south-2` | Read-only `aws ecs describe-services` targeted cluster `eci-cluster-dev`, service `eci-api-dev`. Exit 255: `Your session has expired. Please reauthenticate using 'aws login'.` No deployment result returned. | BLOCKED |
| PostgreSQL Alembic revision | No live revision evidence obtained. Readiness does not establish `22b0001`. Previous operator-supplied revision remains unverified in this attempt. | BLOCKED |
| Existing Entra identity and mapped owner | No authenticated browser/session tool is exposed; no application bearer/session handle was provided in the process environment or inspected repository configuration. Authentication configuration is present, but configuration does not provide an authenticated user session. The same verified identity could not be established. | BLOCKED |
| Authenticated Work Items listing | No authenticated request sent; blocked by unavailable Entra session | BLOCKED |
| Existing owned XLSX Candidates evidence | No authenticated request sent; existing source ownership and identity continuity could not be independently verified | BLOCKED |
| Previous fixture execution check | Preparation record contains no returned item ID or executed write; live existence was not queried because authentication was unavailable | BLOCKED |

The initial sandbox liveness attempt failed with a sanitized `ConnectError`; the initial sandbox AWS attempt could not connect to the regional AWS sign-in endpoint. Approved network escalation allowed both public health checks to succeed and exposed the AWS session-expiration blocker. These connectivity attempts were read-only and carried no application bearer token.

The AWS session issue concerns cloud inspection credentials only. Restoring that session would not authenticate an application user. The Entra session issue is separate: the report's MSAL mechanism exists in source, but this agent has no accessible signed-in browser session or approved in-process authentication handle for the existing user. No token values, raw claims, secrets, or existing analysis contents were printed, exported, persisted or disclosed. No browser-profile or credential-cache extraction was attempted.

| Approved lifecycle checkpoint | Actual observation | Result |
|---|---|---|
| W1 — create + owned detail/history | Not sent; preflight incomplete | BLOCKED |
| W2 — exact creation replay + history comparison | Not sent | BLOCKED |
| W3 — in_progress + detail/history | Not sent | BLOCKED |
| W4 — completed + detail/history | Not sent | BLOCKED |
| W5 — reopen + detail/history | Not sent | BLOCKED |
| W6 — cancelled + detail/history | Not sent | BLOCKED |
| W7 — archive + archived detail/history | Not sent | BLOCKED |
| W8 — restore + final detail/history | Not sent | BLOCKED |

Final sanitized state: **unobserved**. No item UUID was returned, and item status, version, archive state, event count and provenance count cannot be reported as live facts. The desired cancelled/version-7/seven-event/zero-source state remains an expectation only. This execution attempt issued zero lifecycle POST requests and made no application/database writes. There is no uncertain write outcome to reconcile from this attempt.

Deviation: execution stopped at the preflight boundary; no deviation from the approved fixture, request bodies, operation order or expected versions occurred. Existing ECS revision, rollout, migration and authenticated-source claims remain operator-reported evidence, separate from the two observed public HTTP successes. No lifecycle checkpoint is marked FAIL because none was attempted; all are BLOCKED by missing prerequisites.

Operator involvement needed before resumption: restore the existing authorized AWS inspection session through the established login process and make the existing authorized Entra application session securely accessible through the established mechanism, including the known persisted source reference used in the earlier validation. Do not paste or attach bearer tokens. No substitute authentication flow is authorized or proposed. On resumption, repeat read-only preflight before any W1 request; approval for the unchanged W1–W8 remains recorded.

Execution completion record:

- Modified only `docs/codex/reports/phase_22g_report.md`; no application source/configuration changes or new fixture.
- AWS resources accessed: API CloudFront public health/readiness paths; ECS describe attempted but blocked by expired credentials. No infrastructure, IAM, ECS/ECR, schema or Azure changes.
- Migration/database writes, mailbox operations, attachment retrieval, AI inference, email sending, cleanup and Git operations: none.
- Tests: no tests rerun during this live attempt. Preparation's 85 passing local tests remain local evidence only.
- Phase 22G remains incomplete and blocked. No frontend deployment or later phase started.

## Authentication limitation and operator handoff — 2026-09-28

This addendum preserves all preceding execution evidence and supersedes the earlier outstanding AWS-login prerequisite and proposed Codex session-access resumption path. The operator has restored AWS CLI authentication for account `034456343525`, IAM user `eci-developer`, profile `eci-dev`, region `eu-south-2`. The operator independently verified ECS cluster `eci-cluster-dev`, service `eci-api-dev`, task definition `eci-api-dev:14`: ACTIVE, desired/running/pending tasks 1/1/0, primary rollout COMPLETED, backend and ClamAV containers RUNNING, existing `DATABASE_URL` secret reference confirmed, and ECS Exec disabled. These are operator-verified observations, not fresh Codex cloud checks.

The operator previously verified the PostgreSQL migration `21d0001 → 22b0001`; it must not be repeated. CloudFront health/readiness PASS refers to the recorded HTTP 200 observations above, not new requests during this handoff.

The operator confirms that no approved authenticated browser-session bridge is available to this execution environment. The repository's MSAL silent-acquisition/request mechanism requires the existing authenticated application session; restored AWS CLI credentials do not provide that application identity. Codex cannot establish access as the same principal used for the successful Work Items listing and owned XLSX Candidates retrieval. Entra authentication access from Codex therefore remains BLOCKED, and W1–W8 must not execute from this environment without that identity.

No further authentication workaround will be attempted. Authentication material must not be extracted from browser profiles, caches or credential stores; bearer tokens must not be printed, exported, persisted, logged or disclosed, or requested from the operator. No alternative identities or authentication mechanisms, OIDC/MSAL/IAM/security-setting changes, or frontend deployment are authorized to resolve this limitation.

Previous authorization for the unchanged synthetic fixture and exact W1–W8 remains recorded; it does not waive identity or preflight requirements. The next execution path is operator-controlled lifecycle validation using the existing authenticated browser session and the report's unchanged procedure, same-principal ownership checks, sanitized evidence requirements and stop conditions. No lifecycle success or returned fixture ID is claimed. The Phase 22 frontend remains undeployed to AWS, and Azure Phase 22 has not started.

This handoff modifies only this report. No additional cloud operations, application/database writes, migrations, deployments, source/configuration modifications or Git operations were performed for this addendum. No tests were run for this documentation-only update; previous test evidence remains unchanged. Phase 22G remains incomplete.

- AWS authentication: operator restored.
- ECS revision 14: independently verified by operator.
- CloudFront health/readiness: PASS.
- Entra authentication access from Codex: BLOCKED.
- W1–W8: NOT EXECUTED.
- Application writes: ZERO.
- Next execution path: operator-controlled lifecycle validation using the existing authenticated browser session.

## Approach B script preparation — 2026-09-28 (no execution authorization)

Prepared [`../scripts/phase_22g_browser_validation.js`](../scripts/phase_22g_browser_validation.js) for independent operator review. This preparation does not exercise or mark W1–W8 as executed. The operator reports the existing Entra browser session is operational and prior deployment, authentication, listing and Candidates checks passed; no fresh live checks were made here. The current instruction authorizes preparation/local review only and requires **separate execution authorization**, irrespective of historical approvals above.

**Browser/authentication mechanism:** the file declares an inert factory and performs no requests on load. Ordinary Chrome DevTools cannot safely obtain the required application handles: `frontend/src/main.tsx` holds `msalInstance` and the API client in lexical scope; `MsalAccessTokenProvider` is constructed privately, and React auth context does not expose it. No supported global bridge was found. Pasting this file into the existing tab alone therefore cannot run authenticated validation. Do not recover those handles through React internals, browser storage, cookies, caches, token interception, or token copying.

The minimal proposed implementation, requiring separate source/integration authorization, is to retain the existing `MsalAccessTokenProvider` in a private variable in the frontend composition scope, share it with the existing API client, and pass that same provider, `msalInstance`, and `config.apiBaseUrl` into `createPhase22GValidation`. Bind the returned one-shot runner to a private operator-controlled button after MSAL is idle. Do not expose the provider, MSAL instance or tokens globally. This uses the existing provider's configured ECI scopes and `acquireTokenSilent`; it creates no new MSAL instance or identity. The runner additionally requires an explicit active account and checks its in-memory identity metadata before/after acquisition and after responses, without logging identity fields. Missing active account or interactive authentication requirements stop the run. The integration is a proposal only: no frontend changes, build or deployment were performed. Any delivery/deployment needed to provide that button requires its own authorization.

The existing high-level API client is not sufficient for this validation because it discards successful HTTP status/Location and does not reject redirects. The proposed runner therefore uses the existing token provider with a narrow fetch wrapper, keeping tokens only in the request's local memory. It rejects redirects, omits cookies, disables request caching and referrers, and never logs response bodies, raw errors, headers or credentials. The source CORS configuration exposes `Location`; deployed CORS access and header exposure remain prerequisites. A missing header stops the run after the write, not proof that creation failed.

**Controls and scope:** only the report's exact W1–W8 POST bodies and fixed creation key are present, with identical serialized W1/W2 bodies. The allowlist fixes `https://dnookm0ucbhv1.cloudfront.net`, the creation endpoint, and only the W1-returned UUID's status/archive/restore/detail/history paths. Each POST requires a separate confirmation; execution is sequential with a one-shot guard, fixed expected versions, no mutation retries or resume path. Owned detail/history is checked after every step, including archive. Assertions cover fixture fields, manual origin, zero sources/context, terminal timestamps, replay equality, exact event metadata/order/IDs/versions, unchanged earlier events, seven final events and an empty offset-7 page. Exact response-field checks reject identity or historical content fields. Only sanitized HTTP/path, UUID and assertion summaries are emitted.

W1 HTTP 200 triggers owned read-only reconciliation and a stop: the fixture may already exist. A POST transport/timeout/body-read failure triggers detail/history reconciliation when the W1 UUID is known and the same account remains available, then stops unconditionally. With a lost W1 response and no UUID, reconciliation is unavailable: the API has no creation-key GET, so the script neither enumerates unrelated records nor sends a recovery POST. This stricter no-replay-on-uncertainty rule governs this proposed script and supersedes the earlier possible use of W2 to recover a lost W1 response. Reconciliation failure also stops; it never permits another write. Do not reload/recreate the runner to resume an interrupted attempt or use a replacement key.

**Operator prerequisites:** review the script and obtain separate execution authorization; authorize/establish the private frontend integration; verify the same existing mapped account, idle MSAL, prior approved deployment/schema and fresh read-only preflight evidence, exact API origin, and no prior fixture attempt/concurrent tab. The script records an explicit operator confirmation of those prerequisites; it does not independently prove them or issue health, list or Candidates calls outside its narrow allowlist. If fresh proof is needed, use the report's separately approved read-only procedure before invoking the runner. Preserve the sanitized synthetic UUID and last verified state for review after any stop.

Expected final state remains **one manual synthetic item, cancelled, unarchived, version 7, seven ordered events, zero sources, no Business Context and no replay event**. API replay/detail/history checks provide application-level evidence, not an independent database row-count audit. No final state has been observed by this preparation.

Files: created only the script above (the new `docs/codex/scripts` directory conflicts with no inspected convention); appended only this report. Existing implementation and earlier evidence preserved. Application source, migrations, infrastructure/cloud configuration and resources touched: none. Git operations, application POSTs and browser execution: none. Local validation results are recorded below.

Local validation: `node --check docs/codex/scripts/phase_22g_browser_validation.js` **PASS** after correcting a strict-mode directive placement caught by the initial syntax check. A TypeScript AST parse (without evaluating the script) confirmed an inert top level, all **8/8** step bodies/paths matching this report, identical creation/replay bodies, fixed origin, expected HTTP statuses/versions/statuses, a single guarded fetch site and single sanitized console site, and no credential-storage access or interactive login calls. Non-Git whitespace/final-newline/conflict-marker checks passed for both deliverables. Browser/runtime tests: **0**, intentionally not executed. No backend/frontend suites or builds were run because application source was unchanged. These static checks do not validate live authentication, deployed CORS, networking or lifecycle outcomes. **W1–W8 remain NOT EXECUTED; await operator review and separate integration/execution authorization.**

## Phase 22G — Operator-Controlled AWS Lifecycle Execution (Actual Results)

### 1. Execution method and evidence provenance

The operator separately executed the previously approved fixed W1–W8 sequence using operator-controlled Chrome DevTools requests against `https://dnookm0ucbhv1.cloudfront.net`, authenticated with the existing authorized Microsoft Entra OIDC application identity. The observations below were supplied by the operator; Codex did not execute or independently reproduce these requests. This evidence does not establish that the prepared Approach B script or its proposed frontend integration was used or deployed.

The earlier Codex attempt remains correctly **BLOCKED before W1**, with no lifecycle writes. The subsequent operator browser execution is a distinct attempt and provides the actual successful lifecycle evidence.

- Synthetic creation key: `phase22g-20260928-3d55c464-c7cf-4752-b45f-6bc5d9885a65`.
- Actual W1-returned Work Item UUID: `64eacb70-c76d-4da4-b0aa-df7908cf686f`.

Only sanitized observations are recorded. Execution timestamps and request IDs were not supplied and are not inferred. No credentials, token claims, cookies, full browser dumps or unrelated records are included.

### 2. Actual W1–W8 results

| Step | Operation | Actual response | Observed state | Assessment |
|---|---|---|---|---|
| W1 | Create fixed manual Work Item | HTTP 201 | `open`, version 1 | PASS |
| W2 | Replay identical creation | HTTP 200 | Original item, version 1; exactly one creation event retained | PASS |
| W3 | Open → In progress | HTTP 200 | `in_progress`, version 2 | PASS |
| W4 | In progress → Completed | HTTP 200 after the interruption documented below | `completed`, version 3 | PASS after reconciliation and authenticated resubmission |
| W5 | Completed → Open, explicit reopen | HTTP 200 | `open`, version 4 | PASS |
| W6 | Open → Cancelled | HTTP 200 | `cancelled`, version 5 | PASS |
| W7 | Archive | HTTP 200 | `cancelled`, archived, version 6 | PASS |
| W8 | Restore | HTTP 200 | `cancelled`, restored, version 7 | PASS |

All eight approved operations ultimately returned their expected successful responses. The initial unsuccessful W4 request is additional to these eight successful responses and is not counted as a successful lifecycle mutation.

### 3. W4 HTTP 401 interruption and reconciliation

The first W4 attempt returned **HTTP 401**. The operator then performed read-only reconciliation of the same synthetic Work Item. That read returned **HTTP 200**, status `in_progress`, version **2**, completed **false**, archived **false**, and cancelled **false**. This observation showed that the item remained at the W3 state; the 401 is not evidence of completion or any successful mutation.

The operator refreshed the existing frontend session and used an updated authenticated request. W4 then succeeded with the unchanged approved body:

```json
{"expected_version":2,"status":"completed","reopen":false}
```

The successful response was **HTTP 200**, status `completed`, version **3**. The completion timestamp was populated and matched `updated_at`; archived was **false**. This was an operator-controlled continuation following reconciliation, not a Codex retry or evidence that the prepared script automatically resumed.

### 4. Detail and event-history observations

The operator performed authenticated read-only detail/history verification between lifecycle operations. Creation replay retained exactly one creation event and did not append another event. The observed history contained seven correctly ordered events, with item versions **1–7** and ordinal **0** for every event:

| Version | Event | Observed metadata |
|---|---|---|
| 1 | `created` | `status=open`, `due.kind=none`, `creation_origin=manual` |
| 2 | `status_changed` | `open` → `in_progress` |
| 3 | `status_changed` | `in_progress` → `completed` |
| 4 | `status_changed` | `completed` → `open` |
| 5 | `status_changed` | `open` → `cancelled` |
| 6 | `archived` | `{}` |
| 7 | `restored` | `{}` |

The final event was `restored`, version **7**, ordinal **0**, metadata `{}`. The final event-history request with `limit=100&offset=7` returned **zero additional events**. These are authenticated API observations, not independent direct PostgreSQL row-count verification.

### 5. Final fixture state

| Property | Actual read-only observation |
|---|---|
| Work Item UUID | `64eacb70-c76d-4da4-b0aa-df7908cf686f`, matching the original W1 UUID |
| Creation origin | `manual` |
| Status | `cancelled` |
| Version | 7 |
| Archived | false |
| Cancelled timestamp | Present |
| Completed timestamp | Absent |
| Business Context | `null` |
| Sources | 0 |
| Event count | 7 |
| Additional events after offset 7 | 0 |

The synthetic Work Item remains **restored, unarchived and cancelled**. No additional cleanup, hard deletion or archive operation was performed.

### 6. Acceptance-criteria assessment

| Criterion from the fixed procedure | Assessment against supplied observations |
|---|---|
| Fixed manual fixture creation and identical replay | PASS: W1 201; W2 200, original item/version 1, no additional creation event |
| Approved lifecycle transitions and optimistic versions | PASS: successful W3–W8 responses match the prescribed states and versions 2–7 |
| W4 completion and authentication interruption handling | PASS: 401 recorded separately; read-only reconciliation retained version 2; unchanged W4 body then produced version 3 with completion timestamp matching `updated_at` |
| Explicit reopen, cancellation, archive and restore | PASS: expected states observed; final item cancelled and unarchived, with cancellation timestamp present and completion timestamp absent |
| Ordered audit history and replay idempotency | PASS: seven events, expected types/metadata, versions 1–7, ordinal 0; replay added no event; offset-7 page empty |
| Final identity, origin, context and sources | PASS: original fixture UUID, manual origin, null Business Context and zero sources |
| Independent database counts and full low-level assertions | Not independently verified; evidence is limited to the supplied authenticated API observations |

**Phase 22G AWS backend lifecycle validation: PASS** on this operator-observed evidence. The supplied observations do not separately document every original low-level assertion, including `Location` equality, replay timestamp/event-ID equality, event-ID uniqueness, event context IDs, timezone checks, response-field omission checks, or preservation of the exact cancellation timestamp through archive/restore. They also do not independently measure database item/source/event/identity row counts or establish local/deployed artifact equivalence. No new claim is made for those checks. A single authorized identity does not prove live cross-owner isolation; the original exclusions for negative transitions, races, due dates, contexts, provenance/candidate conversion and external execution remain.

### 7. Remaining Phase 22G deployment work — historical, before 2026-09-29 frontend deployment

- **AWS Phase 22 frontend deployment: NOT STARTED.** A separate readiness assessment and explicit operator authorization are required before deployment begins.
- **Azure Phase 22: NOT STARTED.** No Azure rollout is established by these AWS lifecycle observations.
- **Overall Phase 22G cloud rollout: INCOMPLETE, not CLOSED.** Backend lifecycle PASS does not complete the remaining deployment work.

Documentation consolidation scope: modified only `docs/codex/reports/phase_22g_report.md`; no other files created or modified. No cloud requests, database queries, lifecycle operations, migrations, deployments or Git commands were performed for this update. No application tests or builds were run for this documentation-only task, and prior test evidence remains historical. Application/frontend source, the browser validation script, migrations, infrastructure configuration and deployment artifacts were preserved; Phase 22 source changes remain intentionally uncommitted. No next deployment or phase was started.

## AWS frontend deployment and operator-controlled browser acceptance — 2026-09-29

### 1. Evidence provenance and authorization

**AWS Phase 22 deployment and scoped frontend/browser acceptance: PASS.** The operator manually completed the bounded deployment and read-only browser acceptance on 29 September 2026. All new live results below are supplied operator evidence; Codex did not execute or independently reproduce them during this documentation update. The earlier Codex attempt remains **BLOCKED before W1**, separate from the successful operator W1–W8 execution and this subsequent frontend acceptance. W1–W8 were not repeated and no further lifecycle writes were performed.

The operator explicitly authorized the bounded frontend deployment and contingency rollback, accepting the documented limitations of the preserved public-byte rollback baseline for this development deployment. The existing `eci-phase16d-spa-publish-temp` IAM policy was inspected: it grants `s3:PutObject` on the frontend bucket and `cloudfront:CreateInvalidation` / `cloudfront:GetInvalidation` on the SPA distribution. **No IAM policy was changed.** Successful publication and invalidation do not establish that every contingency rollback operation was tested.

| Deployment identity / target | Operator-supplied value |
|---|---|
| AWS profile | `eci-dev` |
| Account | `034456343525` |
| IAM user | `eci-developer` |
| Region | `eu-south-2` |
| S3 bucket | `eci-web-aws-dev-034456343525` |
| CloudFront SPA distribution | `E1XFNK98P7PU2W` |
| Frontend URL | `https://d1ut7j94w7lt3b.cloudfront.net` |

### 2. Published artifact and invalidation

The operator verified the approved candidate manifest SHA-256: `4b684dfbf2d630ec6a2adb045a275737257a75a36bf32c60aafbd650cee099ac`. This matches the artifact identity recorded in the [frontend readiness assessment](phase_22g_frontend_readiness_report.md#6-local-validation-results-and-exact-artifact); no rebuild is implied.

All eight approved assets were uploaded successfully. The operator independently checked each through the public CloudFront endpoint using SHA-256 and HTTP Content-Type checks before publishing the entry:

| Asset | Public hash and Content-Type verification |
|---|---|
| `assets/index-dYbR60Oz.js` | PASS |
| `assets/index-Gheok34O.css` | PASS |
| `assets/permissions-CAx5a8kf.js` | PASS |
| `assets/WorkItemsListPage-BnPbMiyz.js` | PASS |
| `assets/WorkItemDetailPage-BIYaHGaG.js` | PASS |
| `assets/WorkForm-CoxQFf2V.js` | PASS |
| `assets/ContextWorkspacePage-MZDC2C5y.js` | PASS |
| `assets/MailboxWorkspacePage-EuPBlbHK.js` | PASS |

The previous Phase 21 public `index.html` was verified locally and against the live frontend immediately before replacement: SHA-256 `0e54cf5a82e2a083f64b4abb4be0f7b51a1343cd1fcd77818c1e9b6fc88a2ff3`. The operator then uploaded the validated Phase 22 `index.html` and successfully verified its published SHA-256: `0dbb410f916fb0d0d9277ac5313a49099bef4b2ae6607faa89e07b4822a44a86`.

| CloudFront invalidation | Result |
|---|---|
| Distribution | `E1XFNK98P7PU2W` |
| Path | `/*` |
| Invalidation ID | `IBTTWV25MGS4CFJDFY0I466T5W` |
| Final status | **Completed** |

No previous assets were deleted. This evidence records the SPA publication only; it does not imply another backend deployment or migration.

### 3. Rollback evidence and accepted limitations

The previous Phase 21 public frontend files were preserved locally under `.phase22g-frontend-readiness-20260929/public-current-frontend/`. The verified prior entry hash above links that preserved public-byte copy to the frontend served before replacement.

This is a **public-byte backup, not an exact S3 object/version backup**. AccessDenied responses prevented the deployment identity from inspecting certain original S3 metadata, encryption settings and bucket versioning. The operator explicitly accepted those limitations for this development deployment. Bucket versioning and exact original S3 metadata remain unverified; full rollback operations were not independently tested. **No rollback was necessary or executed.** Frontend rollback authority did not authorize backend/schema rollback or fixture changes.

### 4. Authenticated browser acceptance

The operator used the existing authorized Microsoft Entra session. These are operator-observed browser and API results, not Codex browser execution or independent database verification. Screenshots do not independently establish internal database state.

| Observed browser check | Result |
|---|---|
| AWS application loads correctly; existing authenticated session works | PASS |
| Platform Owner and AWS indicators display | PASS |
| Tracking appears in navigation | PASS |
| Tracking listing renders the existing synthetic Work Item | PASS |
| Work Item detail renders successfully | PASS |
| Direct detail URL loads and survives browser reload | PASS |
| Authentication session persists after reload | PASS |
| Seven audit-history events display in the correct order | PASS |
| Console shows no visible JavaScript, CORS, authentication or chunk-loading errors | PASS |
| Business Context listing loads | PASS |
| Tracking empty-state filtering works | PASS |
| Resetting Status to All statuses restores the existing synthetic Work Item | PASS |

Authenticated Network-panel observations:

| Request | Result |
|---|---|
| GET `/api/v1/me` | HTTP 200 |
| GET `/api/v1/work-items/64eacb70-c76d-4da4-b0aa-df7908cf686f` | HTTP 200 |
| GET `/api/v1/work-items/64eacb70-c76d-4da4-b0aa-df7908cf686f/events?limit=20&offset=0` | HTTP 200 |

The observed existing fixture `64eacb70-c76d-4da4-b0aa-df7908cf686f` retains **Manual** origin, status **cancelled**, archive state **Unarchived**, version **7**, **0** source associations and **7** audit events, ending in **restored**. The frontend acceptance involved no further lifecycle mutation, fixture creation or cleanup. Displaying Platform Owner does not establish a bypass of object ownership.

### 5. Acceptance boundaries and final Phase 22G status

| Completed scope | Assessment |
|---|---|
| Phase 22 local implementation and validation | PASS, historical Phase 22F and frontend readiness evidence |
| AWS database migration and backend deployment | PASS, previously recorded operator evidence; unchanged by this update |
| Operator-executed W1–W8 lifecycle validation | PASS, historical authenticated API observations, including separate W4 reconciliation |
| AWS frontend deployment | PASS, operator-executed publication, eight asset checks, entry hash and completed invalidation |
| Core authenticated frontend browser acceptance | PASS, limited to the observations above |
| Azure Phase 22 | **NOT STARTED** |
| Overall Phase 22G | **INCOMPLETE, not CLOSED**; scoped AWS PASS does not establish every original acceptance criterion or Azure rollout |

Against the original [frontend checklist](phase_22g_frontend_readiness_report.md#10-operator-controlled-browser-acceptance-checklist--not-run), the following closure evidence remains outstanding:

- Live Business Context-to-Tracking integration with an existing authorized context: **NOT RUN**; a successful Business Context listing does not establish this integration.
- Deliberately observed loading states under GET throttling and induced recoverable frontend read-error handling: **NOT RUN**. Empty-state filtering passed, but is not evidence for these separate checks.
- Complete checklist-level evidence is not supplied for every network/security assertion (including the listing HTTP status and explicit mixed-content/unexpected-redirect checks), nor for a post-publication distribution `Deployed` status. These are **not independently verified**, not failed checks.
- The original lifecycle section's low-level assertion and artifact-equivalence gaps remain as documented in its acceptance assessment. This browser acceptance adds no direct SQL verification of the final fixture, row counts or database identity state.
- The readiness assessment's separate acceptance of the unchanged hosting security-header/TLS posture is not explicitly supplied here. Acceptance of the public-byte rollback limitations must not be broadened into that separate decision.

Unconditional closure would require the remaining in-scope evidence or an explicit operator decision narrowing/accepting those criteria, plus a separate disposition of the still-unstarted Azure rollout. This report neither authorizes nor performs additional checks or deployment.

The following were **not independently exercised during frontend acceptance**: live mailbox and attachment workflows; candidate confirmation or AI inference; additional lifecycle mutations; cross-owner or additional-identity testing; and direct SQL verification. They remain excluded or unverified coverage, not PASS results or instructions to expand the browser scope. Phase 22F's broader proposed live checks remain local/preparation evidence unless separately recorded as completed. Existing local attachment/XLSX regression evidence is preserved without claiming live coverage.

### 6. Documentation-only completion record

Modified only `docs/codex/reports/phase_22g_report.md` and appended a dated post-assessment addendum to `docs/codex/reports/phase_22g_frontend_readiness_report.md`. No files were created. Earlier readiness conclusions, blocked Codex execution, successful manual operator lifecycle evidence and prior test counts remain historical and distinguishable.

No cloud resources were touched by this documentation task. No AWS CLI, Azure operation, deployment, public or authenticated HTTP request, backend/database operation, lifecycle write, mailbox access, attachment retrieval, AI inference, Send, dependency installation, application rebuild or Git operation occurred. Application source, tests, configuration, infrastructure and migrations are unchanged; the AWS backend, PostgreSQL database and synthetic fixture remain unchanged by this task. No application tests were run (0); prior passing counts were not rerun or added together. Validation is limited to local documentation consistency, preservation, links and whitespace checks. No later phase was started.

## Closure addendum — 2026-10-02

Phase 22 implementation is committed and pushed to `master`: **`46128f261857cfe041c1caadcc679452d03b0967`** (short **`46128f2`**), subject **`feat: add Phase 22 action and obligation tracking`**. Local inspection on 2026-10-02 found a clean working tree and `HEAD`, `master` and the local `origin/master` reference at that commit. Push completion and **CI PASS** are operator-supplied evidence: GitHub Actions workflow **CI**, branch **master**, event **push**, run **`36846483687`**, observed title “feat: add Phase 22 action and obligation ...”. No remote, CI or cloud checks were repeated for this documentation update.

### Separate evidence and completed scope

- **Local validation complete:** historical [Phase 22F evidence](phase_22f_report.md); no application suites rerun for this closure.
- **AWS scoped deployment/browser validation complete:** the preceding operator-observed migration/backend, W1–W8, frontend publication and browser results remain the AWS evidence. The AWS fixture, rollback limitations and outstanding acceptance checks are unchanged.
- **Azure backend/lifecycle/frontend/browser validation complete:** separately supplied operator observations are recorded in the [Azure closure addendum](phase_22h_azure_readiness_report.md#closure-addendum--2026-10-02), including schema `22b0001` and the retained Azure cancelled/restored version-7 fixture. Azure success does not fill gaps in AWS acceptance.
- **Source committed and pushed; CI passed:** as recorded above, separately from local and cloud validation.

The earlier “Azure NOT STARTED” and “INCOMPLETE, not CLOSED” statements describe their dated assessments. Deployment and scoped validation are now complete on both clouds; this addendum does not claim every original Phase 22G criterion passed or unconditional production readiness. AWS context-to-Tracking, loading/read-error, network/security, distribution-state, hosting-posture and low-level assertion/artifact-equivalence gaps remain as documented above.

Mailbox attachment regression was not revalidated in this closure. Production-scale load/recovery was not tested; PITR was not rehearsed; full disaster recovery was not tested. The ignored `.phase22g-frontend-readiness-20260929/` and `.phase22h-readiness-20260929/` directories remain local deployment/rollback evidence, not source-controlled runtime content. No readiness or rollback artifacts were changed. This task performs documentation edits only: no application/migration changes, cloud operations, fixture writes, commit or push.
