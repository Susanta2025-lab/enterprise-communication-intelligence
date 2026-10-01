# Phase 22F — Local Hardening & Release Readiness

Date: 2026-09-27. Scope: authorized local hardening and validation only. **Verdict: PASS — Phase 22F local release-readiness gates complete.** Phase 22G has not started and Phase 22 is not declared closed.

## 1. Verified baseline and interruption recovery

Initial and resumed branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index empty. Repository migration head: sole `22b0001`. The complete starting inventory contained 84 modified/untracked files; `.phase22f-initial.log` records status, branch, HEAD, index and SHA-256 for each. The inventory is reproduced below. No baseline conflict or material architectural contradiction with ADR-030 was found.

Read AGENTS.md, ADR-030, the Phase 22 roadmap, readiness assessment and 22A–22E reports. The roadmap's early planned-status language remains historical; the accepted implementation is evidenced by the subsequent reports and actual code. Earlier reports, roadmap, ADR, AGENTS.md and migration files are preserved. The operator's 22E numbers (3,127 backend, 209 PostgreSQL, 419 frontend) are previous-phase evidence, not new execution results.

The operator reported a usage-limit interruption during 22F. Recovery inspected the actual worktree, test file, logs, JUnit and local processes before continuing. No test process remained active at recovery. `tests/postgres/test_work_item_hardening.py` was complete and syntactically valid, with five parametrized cases; two formatting issues were corrected. Recovered evidence:

- Initial 22F baseline: 453 passed in 64.37 s, before hardening regressions.
- Privacy reproduction: 1 failed, 56 deselected in 2.12 s, demonstrating echoed submitted title content. This is deliberately failing defect evidence, not a passing gate.
- Interrupted focused run actually completed: JUnit confirms 462 passed, zero failures/errors/skips, 67.517 s (pytest console 67.53 s). This predates final changes.
- Initial focused frontend: 57 passed in 7.79 s, before additional recovery tests.
- Resumed intermediate backend: 467 passed in 92.79 s, before Unicode validation.
- Intermediate frontend full runs: 426 passed/3 failed in 27.55 s, then 428 passed/1 failed in 27.92 s. The cold lazy mailbox import exceeded the tests' one-second UI wait. The three initial-load waits now allow five seconds, preserving their assertions and leaving application timeouts unchanged.

The final gates below supersede intermediate evidence. Overlapping suites are not additive. No skipped test is counted as passing.

## 2. Implementation review and architecture

| Slice | Reviewed implementation | Finding |
|---|---|---|
| 22A | Accepted ADR B1–B6, due/status/source/history/API contracts and exclusions | Separate tracking aggregate and human-confirmation authority remain intact |
| 22B | Domain, all three SQL models, migration, repository savepoints, UoW, immutable sources and minimal journal | Conditional owner/version writes, atomic events, retained provenance and safe uniqueness recovery preserved |
| 22C | Every manual route, owner lookup, lifecycle, query validation and safe errors | No owner bypass; scoped validation/privacy and calendar-overflow defects corrected |
| 22D | Projection, full-value hashing, source verification, creation replay and exact candidate uniqueness | Full 201–300-character XLSX action observations remain valid; title limit remains 200; no truncation or inferred pairing |
| 22E | Tracking list/detail/forms, candidate review, Context Tracking, merged SQL timeline, identity-bound cache and memory-only recovery | Safe timezone rendering and small route split added; query and identity architecture preserved |

Tracking services depend on identity resolution and database repositories only. AI providers, content-capable mailbox connectors, attachment retrievers/scanners/parsers, credentials, workflow executors and Send are absent from their dependency graph. Existing HTTP sentinels reject construction of external-effect dependencies. Full regressions exercise existing Context, attachment/XLSX, approval/execution and offline Mock/Foundry/Bedrock contracts. No live-provider validation is claimed.

## 3. Security and ownership audit matrix

| Boundary / routes | Enforcement and direct-test evidence |
|---|---|
| All ten tracking routes | Verified authentication plus analyze dependency; absent/invalid token 401, disabled auth 401, missing capability 403; route matrix exercised directly |
| Manual POST and from-analysis | Server maps verified issuer/subject through IdentityResolver to users.id; client owner/actor/status/version/authority fields rejected |
| Mailbox provenance | Additional communications:read derives from verified source metadata, including nested sources |
| Existing-key replay | Stored immutable sources enforce read before replay/hash-conflict disclosure, even after analysis/connector deletion |
| Item/detail/events/mutations | SQL id + user_id predicates; foreign and unknown use identical 404; Platform Owner has no bypass |
| Context selection/filter/timeline | Owned context lookup; active target locked for new association; foreign context never grants item membership |
| Analyses/attachments/connectors | Owned repositories derive source tuple; unknown and foreign return identical 404, including Platform Owner |
| Sources/events/API surface | No public source-write, event-write, hard-delete, Send, execution or automatic-confirmation route |
| Errors/logs | Generic persistence 503 and conflict codes; allowlisted 422 field guidance only; no submitted values, digests, SQL or provider responses in errors/logs |
| CORS | Existing origin/credential restrictions retained; Location exposed only through existing configured CORS policy; owned relative UUID link validation retained |

Permission checks do not use email, mailbox identity, deployment identity or cloud workload identity. Metadata reads need analyze; mailbox-backed creation additionally needs read. Disconnected but retained owned connector metadata remains valid historical provenance. Availability never asserts live provider content exists.

## 4. Defects and precise corrections

### Validation response and telemetry privacy

FastAPI's default RequestValidationError response included `input`, allowing malformed business text, candidate values and unknown fields to be reflected in 422 responses despite Pydantic's hide_input_in_errors setting. Tracking now uses a scoped APIRoute handler. It returns the existing `ErrorResponse` shape with a string detail and only schema-owned top-level field names, for example `Invalid work item request. Review fields: title.` It never serializes Pydantic message/context/input or unknown field names. Body, candidate, query and path regressions verify sanitized responses, safe field guidance and no tracking writes.

Tracking telemetry previously logged a raw path, including malformed item-ID input. It now records a static item-ID placeholder and allowlisted operation suffix. Query values and bodies are not logged. This change is restricted to the tracking path; shared telemetry regressions remain in the full gate. Frontend 422 recovery displays its existing safe guidance and does not render arbitrary server response text.

### Calendar overflow

RFC 3339 values at year 0001/9999 with extreme offsets could raise OverflowError during timezone/UTC conversion, yielding an uncontrolled error. TimedDue now checks representability in UTC and the confirmed IANA zone, translating overflow to validation failure. Typed instant-range filters do the same. Four API cases exercise both ends for creation and filters and require 422, never 500. Ordinary zone matching, explicit fold offsets and date-only semantics remain unchanged.

### Invalid storage text

Inspection reproduced UnicodeEncodeError when escaped unpaired-surrogate input reached request hashing; NUL text also cannot be stored in PostgreSQL text columns. Tracking's common frozen value validation now rejects NUL and unpaired surrogates with a controlled validation error. Six HTTP cases cover title, description and provider-message references, requiring 422 and zero aggregate rows. Valid Unicode retains its original spelling and hashing identity; no normalization or truncation is introduced.

### Browser timezone resilience

A browser lacking a saved server timezone could throw while rendering a timed item or initializing its editor. The display now falls back to the exact saved RFC 3339 value and zone with an explicit browser-support notice. The editor supplies no invented wall time and leaves timezone confirmation unchecked; changing the due value requires explicit review. The backend remains authoritative. Date-only rendering remains a calendar string and never passes through UTC midnight.

Offset enumeration reuses one Intl formatter per review instead of constructing one for every possible minute offset. It still round-trips every candidate and demands an explicit fold choice. Tests cover Lord Howe's half-hour gap/fold, Apia's skipped day, +14/-12 offsets, Kathmandu's 45-minute offset and unsupported historical sub-minute Paris time, which fails closed.

### Small route-loading change

Tracking list/detail, Context workspace and Mailbox workspace use React.lazy under Suspense with an accessible loading status. Route paths, capability gates, the keyed authentication tree, QueryClient lifecycle and creation recovery map are unchanged. Existing error boundary handles module-load failure. No bundler configuration, dependencies or warning threshold changed.

## 5. Provenance and confirmation

Retested field-specific source bounds, complete original-value SHA-256, Unicode/optional-field canonicalization, digest changes, locators, source-type confusion, explicit strict confirmed=true and independent reviewed title/due fields. Candidate projection is read-only. No analysis event, display, selection or cancellation creates a work item. XLSX action/date arrays remain independent and potential amounts are excluded.

New PostgreSQL cases project a candidate, delete its analysis or connector before final confirmation, and require 404 with zero work items, sources or events. Existing cases verify disconnection, retained unavailable sources, replay after deletion/completion/archive and read enforcement from immutable sources. New-key creation cannot reacquire missing sources or fetch content. Sources are immutable after creation and minimal events contain no title/description snapshots.

## 6. Transactions, concurrency and lifecycle

Real PostgreSQL tests force concurrent same-key identical-intent, changed-intent and exact-origin candidate races beyond the absence check. One creation wins; losers replay or receive the documented conflict after savepoint rollback. A transaction remains usable following uniqueness conflict. New HTTP-level races use real offline JWT validation and PostgreSQL, require 201/200 or 201/409, retry the winner as a lost response, verify identical Location/current item and assert one item/one creation event.

Retained tests cover expected-version competitors, validated no-ops, lifecycle matrix, explicit terminal reopening, separate archive/restore, partial source/event insertion, outer rollback and commit failure. Failed writes leave no orphan aggregate rows or inconsistent version. Replay adds no sources or events. Context archive/association lock tests exercise both acquisition orders against actual PostgreSQL UPDATE locks without disabling safety guards.

Date-only overdue SQL is compared to the domain predicate at a single reference instant for each stored zone before pagination. Timed overdue is strictly later than the instant. Completed/cancelled/archived items are excluded. Inclusive date and instant bounds, equal instants with different offsets, contradictory/reversed/mixed ranges and explicit typed due sorting are tested. Browser timezone data may differ; server rejection requires review, never automatic correction.

## 7. Context timeline and query evidence

Production uses a context/owner-scoped UNION ALL projection with one global occurred_at DESC / ID ASC order, explicit C collation on PostgreSQL, and one LIMIT/OFFSET after merging. No owner-wide analysis payload materialization or per-category truncation was added. Current Tracking uses direct current association; timeline work-item entries use committed journal IDs and real occurred_at/context_at_event_id.

Tests preserve original-context history, detachment under the previous context, association under the new context, mutation event ordinal ordering, generic historical titles, owner/Platform Owner isolation and archived-context behavior. Cross-category equal-time pages and page sizes 1/7/20/100 contain no duplicates or omissions on unchanged data.

The representative PostgreSQL test creates 250 context events, 30 foreign events and 500 unrelated owner analyses. Offset 200 returns 20 records through one SELECT without business payload columns. EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) records planning/execution time and returned rows in JUnit. Final complete PostgreSQL run: **0.743 ms execution, 0.784 ms planning, 20 rows returned**. Focused run: 0.833 ms execution, 0.861 ms planning, 20 rows. The full backend repeat measured 0.846 ms execution, 0.805 ms planning, 20 rows. These values were read from this phase's actual JUnit properties.

These are local synthetic measurements, not production throughput or load guarantees. Offset pagination is deterministic for unchanged data, not a snapshot across concurrent requests; deep offsets still require database work. No index or migration change was justified by this evidence. Legacy context archive/restore history retains its existing limited projection; no complete context event sourcing or historical backfill is claimed.

## 8. PostgreSQL safety, schema and migration integrity

Before every test invocation the local runner inspects running `eci-phase22b-postgres`, exact image `postgres:16`, exact binding `127.0.0.1:5435 → 5432`, and configured database `eci_test`. It obtains disposable credentials internally without printing/persisting a connection string, applies the unchanged ECI_POSTGRES_TEST_DATABASE_URL guard, then verifies SQL current_database(), major version 16 and current revision 22b0001. No inherited URL is assumed. Sandbox Docker/local socket access needed approved local execution; no unknown or cloud database was used.

The complete suite checks schema inventory, columns/indexes/checks/uniqueness, SQL NULL combinations, composite child ownership FKs, source/event integrity, current-context SET NULL, opaque retained historical references, and SQL/ORM account-erasure cascades. Existing Phase 20/21 storage remains compatible.

Migration evidence includes the retained data-preserving 21d0001 → 22b0001 rehearsal with XLSX JSON unchanged, empty tracking downgrade/re-upgrade, populated downgrade refusal before DDL, and the new empty-database base → head round trip. The new test first requires every application table to be empty in the guarded disposable fixture and verifies schema absence at base and the complete inventory at head. No populated history is deleted to force downgrade success. Migration 22b0001 and every prior migration are unchanged; no new migration exists.

## 9. Frontend security, resilience and accessibility

The authenticated application tree still owns a fresh QueryClient and memory-only recovery map per identity/authentication state. Identity changes cancel queries/writes, clear the old cache/drafts and reject late success callbacks. Tracking query keys include identity; mailbox/source keys reset candidate selection. No business draft, raw candidate, mailbox content or credential is added to browser storage.

Tests cover navigation/capability gates, pending reads/writes, late responses, stale-version reload, candidate conflicts, preserved creation key/payload after uncertain responses, closing/reopening recovery, read-only terminal/archived controls, context invalidation and unavailable metadata. A new full-application-remount case proves uncertain drafts clear without automatic resubmission; unknown-zone detail/editor and safe 422 cases are also covered.

Existing labeled form/axe, keyboard dialog focus trapping/restoration, error announcements, responsive layout constraints and loading/empty/error tests remain included. The lazy-loading fallback has role=status. This is automated DOM/accessibility and source review evidence, not a manual screen-reader or multi-browser visual audit.

Creation recovery intentionally remains memory-only. Closing/reopening within the signed-in application reuses the exact original request. Reload/sign-out clears it. The form now explicitly instructs the user to inspect Tracking after refresh before submitting a new creation. No automatic duplicate creation occurs; a deliberate new-key manual submission after losing recovery state can duplicate business intent. Exact-origin candidate uniqueness still applies to confirmed analysis items.

## 10. Final local validation

| Test gate | Passed | Failed | Errors | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Focused backend hardening | 473 | 0 | 0 | 0 | 118.993 s |
| Complete guarded PostgreSQL | 214 | 0 | 0 | 0 | 16.476 s |
| Complete backend (includes PostgreSQL) | 3147 | 0 | 0 | 0 | 212.884 s |
| Focused frontend (2 files) | 60 | 0 | 0 | 0 | 7.87 s |
| Complete frontend (32 files) | 429 | 0 | 0 | 0 | 29.54 s |

Durations for backend rows are JUnit suite timings; pytest console rounded them to 119.00 s, 16.48 s and 212.91 s. Frontend duration is the Vitest wall duration. Phase 22F adds 20 backend tests (15 HTTP and 5 PostgreSQL) and 10 frontend tests to the prior-phase baseline.

| Additional check | Result | Wall duration |
|---|---|---:|
| `npm run typecheck --prefix frontend` | PASS | 5.834 s |
| `npm run lint --prefix frontend` | PASS | 4.046 s |
| `npm run build --prefix frontend` | PASS | 7.410 s |
| `python -m ruff check .` | PASS | 0.061 s |
| `python -m pip check` | PASS | 0.410 s |
| `git diff --check` | PASS | 0.019 s |
| `python -m alembic heads` | PASS | 0.486 s |

Pip reports no broken requirements; its non-writable cache warning is environmental only. Alembic output is exactly `22b0001 (head)`. Build succeeds with the documented advisory size warning. No required check is blocked.

Production build: PASS. Main JavaScript chunk **513.08 kB (141.64 kB gzip)**, compared with the historical 22E **694.82 kB (193.14 kB gzip)**. Reduction: 181.74 kB minified / 51.50 kB gzip (about 26%). Separate chunks: Tracking detail 5.68/2.20 kB, Tracking list 5.77/1.85 kB, Context workspace 10.86/2.90 kB, shared WorkForm 11.79/4.56 kB, Mailbox workspace 50.03/12.66 kB and a shared permissions/dependencies chunk 101.04/33.92 kB (minified/gzip). CSS 23.83/5.60 kB. These are actual Vite outputs, not network-performance measurements. The main chunk remains 13.08 kB above Vite's 500 kB advisory threshold; the warning is retained and documented. Further bundling redesign solely to remove this non-failing warning was not justified. Local artifact SHA-256: `frontend/dist/index.html` = `540af0f0873aa3f972dcea45f043e5dffada90c84d7f37219700bb60b5972d77`; main `index-DSWks3CN.js` = `791ac5dc1fa6bc2d74e30ee2c955c97ad35117df340ab84e77cc40453cade249`. `.phase22f-artifacts.log` records all local build hashes; no artifact was uploaded.

Local evidence files: `.phase22f-focused.junit.log`, `.phase22f-postgres.junit.log`, `.phase22f-full.junit.log`, matching pytest console logs, `.phase22f-frontend-focused.log`, `.phase22f-frontend-full.log`, `.phase22f-checks.log`, and `.phase22f-initial.log`. These ignored diagnostic artifacts contain no credentials and are not staged. Standard commands executed through the verified local runner or directly:

```sh
python .phase22f-local-tests.log focused
python .phase22f-local-tests.log postgres
python .phase22f-local-tests.log full
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run test --prefix frontend -- --run
npm run build --prefix frontend
python -m ruff check .
python -m pip check
git diff --check
python -m alembic heads
```

The runner dispatches pytest -q with JUnit output and the guarded dedicated database URL. It repeats target verification on each invocation. No test is silently substituted with SQLite; the full backend includes the real PostgreSQL suite. Additional schema/security/provider/accessibility checks are part of these suites and the existing CI inventory. All 90 changed/untracked text files were also explicitly checked for trailing whitespace and conflict markers; report links resolve locally and protected-file preservation hashes match. No external package installation or provider call was needed.

## 11. Exact file changes and preservation

Added:

- `tests/postgres/test_work_item_hardening.py` — five PostgreSQL HTTP race/source disappearance/fresh migration cases.
- `docs/codex/reports/phase_22f_report.md` — this completion and release-readiness report.

Modified/extended by 22F (13 files):

- `app/api/routes/work_items.py` — scoped safe field-level 422 handling and ErrorResponse schema.
- `app/api/middleware.py` — sanitize tracking path parameters in telemetry.
- `app/domain/models/work_item_due.py` — safe calendar conversion and UTF-8/storage-text validation.
- `app/domain/models/work_item_query.py` — controlled range conversion overflow.
- `frontend/src/App.tsx` — four lazy route imports and loading boundary.
- `frontend/src/components/workItems/WorkForm.tsx` — unknown browser-zone editor handling and reload recovery guidance.
- `frontend/src/lib/workItemDue.ts` — readable unknown-zone fallback, safe editor initialization and formatter reuse.
- `frontend/src/test/workItemDue.test.ts` — seven unusual-offset/browser-zone regressions.
- `frontend/src/test/workItems.test.tsx` — safe 422, unknown-zone editor and full-remount recovery tests.
- `frontend/src/test/mailboxAnalysis.test.tsx` — initial lazy-route wait only.
- `frontend/src/test/mailboxAttachments.test.tsx` — initial lazy-route wait only.
- `frontend/src/test/workflowReview.test.tsx` — lazy-route wait in selection helper only.
- `tests/integration/test_work_items.py` — 15 new privacy/calendar/Unicode cases, including schema guidance and zero-write assertions.

75 of the 84 originally modified/untracked files are byte-for-byte unchanged. Nine pre-existing Phase 22 files were intentionally extended as listed; the other four modified files were clean tracked files at entry. Every original inventory path remains present. The two added files and four newly modified tracked files bring complete git status to 90 entries. Diagnostic logs/runner are ignored local evidence, not release source. No migration added or modified.

The original uncommitted Phase 22 implementation remains in place; corrections extend only the identified files. No reset/clean/stash/discard, staging, commit or push occurred. AGENTS.md, all 22A–22E reports, readiness assessment, ADR-030, roadmap and every migration remain byte-for-byte unchanged against the starting evidence. No dependency or infrastructure change.

## 12. Limitations, verdict and Phase 22G prerequisites

**PASS — Phase 22F implementation, hardening, final local validation and reporting are complete.** No known critical security/ownership defect, unresolved transaction/provenance-integrity defect, schema defect or failing required gate remains. This is a local verdict only; it does not authorize cloud validation, deployment, staging, commit, push or Phase 22G.

Remaining limitations are explicit: memory-only creation recovery after reload/sign-out; browser/server timezone database differences and no historical sub-minute offset picker; metadata availability rather than live provider existence; human-declared completion; offset-pagination concurrency/deep-offset limits; local synthetic query timings; automated rather than manual multi-browser accessibility evidence; and a non-failing main-chunk warning. No live deployment, load, cloud-provider or mailbox validation is implied by local PASS.

Cloud resources touched: **none**. No Azure/AWS access, cloud database, deployment, paid AI, live mailbox message/attachment retrieval, Send, IAM/secret/resource change or Phase 22G work. No reminders, recurrence, assignment, automated tracking or workflow-semantics change.

Reviewable next-phase plan, not execution authorization:

1. Operator reviews the entire preserved Phase 22 worktree and selects a traceable release artifact; committing remains operator-controlled, and this report's HEAD is the baseline, not a commit containing the uncommitted release. Record the eventual backend image digest and frontend artifact identity before deployment.
2. Obtain explicit named Azure and/or AWS access/deployment/migration authorization and an approved fixture/retention/rollback plan. Follow the existing [Azure runbook](../../../deployment/azure/README.md) and [AWS runbook](../../../deployment/aws/README.md). Their historical resource descriptions are not fresh cloud state.
3. Inspect actual artifact, health, configuration and schema independently per authorized cloud before repeating any operation. Confirm OIDC, CORS and identity separation. Only if needed and separately authorized, apply the reviewed additive chain to 22b0001. Never downgrade populated tracking tables; prefer compatible roll-forward or an explicitly approved retention/export plan.
4. Use approved test identities and existing owned persisted fixtures for manual creation, explicit candidate confirmation, due/status/archive, source retention, context history, retry/conflict and isolation smoke checks. These flows require no paid inference, mailbox fetch, attachment download or Send. If fixtures are absent, request an approved fixture plan rather than retrieving content.
5. Inspect sanitized logs, verify browser route assets and identity switching, record evidence separately for each authorized cloud and state unresolved live limitations. Do not infer Phase 22 closure merely from 22F local results.

Recommended next action after review: explicitly authorize Phase 22G for the named cloud environment(s) and precise operations. **Stop after Phase 22F; wait for that authorization.**

## 13. Complete initial working-tree inventory

```text
 M app/api/dependencies.py
 M app/api/router.py
 M app/application/services/context_timeline.py
 M app/domain/enums.py
 M app/domain/exceptions.py
 M app/domain/interfaces/business_context_repository.py
 M app/domain/interfaces/persistence_unit_of_work.py
 M app/infrastructure/storage/models.py
 M app/infrastructure/storage/repositories/business_context.py
 M app/infrastructure/storage/unit_of_work.py
 M app/main.py
 M docs/decisions/README.md
 M docs/roadmap/README.md
 M frontend/src/App.tsx
 M frontend/src/api/client.ts
 M frontend/src/api/contexts.ts
 M frontend/src/api/errors.ts
 M frontend/src/components/AppShell.tsx
 M frontend/src/components/contexts/copy.ts
 M frontend/src/components/mailbox/AttachmentAnalysisPanel.tsx
 M frontend/src/components/mailbox/AttachmentItem.tsx
 M frontend/src/components/mailbox/AttachmentsSection.tsx
 M frontend/src/components/mailbox/MessageAnalysisSection.tsx
 M frontend/src/hooks/useContexts.ts
 M frontend/src/index.css
 M frontend/src/pages/ContextWorkspacePage.tsx
 M frontend/src/pages/MailboxWorkspacePage.tsx
 M tests/integration/test_cors.py
 M tests/postgres/alembic_checks.py
 M tests/postgres/conftest.py
 M tests/support/in_memory_persistence.py
 M tests/unit/infrastructure/storage/test_alembic.py
 M tests/unit/infrastructure/storage/test_models.py
 M tests/unit/infrastructure/storage/test_phase21d_migration.py
?? AGENTS.md
?? alembic/versions/22b0001_business_work_items.py
?? app/api/routes/work_items.py
?? app/application/services/work_item_provenance.py
?? app/application/services/work_items.py
?? app/domain/interfaces/business_work_item_repository.py
?? app/domain/models/business_work_item.py
?? app/domain/models/business_work_item_event.py
?? app/domain/models/business_work_item_source.py
?? app/domain/models/context_timeline.py
?? app/domain/models/work_item_due.py
?? app/domain/models/work_item_intent.py
?? app/domain/models/work_item_provenance.py
?? app/domain/models/work_item_query.py
?? app/infrastructure/storage/repositories/business_work_item.py
?? app/infrastructure/storage/repositories/context_timeline.py
?? app/schemas/work_items.py
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/codex/reports/phase_22b_report.md
?? docs/codex/reports/phase_22c_report.md
?? docs/codex/reports/phase_22d_report.md
?? docs/codex/reports/phase_22e_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
?? frontend/src/api/workItems.ts
?? frontend/src/components/workItems/CandidatePanel.tsx
?? frontend/src/components/workItems/ContextPicker.tsx
?? frontend/src/components/workItems/WorkError.tsx
?? frontend/src/components/workItems/WorkForm.tsx
?? frontend/src/components/workItems/creationDrafts.ts
?? frontend/src/hooks/useWorkItems.ts
?? frontend/src/lib/workItemDue.ts
?? frontend/src/pages/WorkItemDetailPage.tsx
?? frontend/src/pages/WorkItemsListPage.tsx
?? frontend/src/test/workItemDue.test.ts
?? frontend/src/test/workItems.test.tsx
?? tests/integration/test_work_item_conversion.py
?? tests/integration/test_work_items.py
?? tests/postgres/test_business_work_item_repository.py
?? tests/postgres/test_context_tracking_timeline.py
?? tests/postgres/test_work_item_conversion.py
?? tests/postgres/test_work_item_queries.py
?? tests/unit/application/test_work_items.py
?? tests/unit/domain/test_business_work_item.py
?? tests/unit/infrastructure/storage/test_business_work_item_repository.py
?? tests/unit/infrastructure/storage/test_context_tracking_timeline.py
?? tests/unit/infrastructure/storage/test_phase22b_migration.py
?? tests/unit/infrastructure/storage/test_work_item_conversion.py
?? tests/unit/infrastructure/storage/test_work_item_queries.py
```

## 14. Final branch, HEAD, index and complete working-tree inventory

Branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index: empty (no staged changes). All Phase 22 changes remain uncommitted.

```text
 M app/api/dependencies.py
 M app/api/middleware.py
 M app/api/router.py
 M app/application/services/context_timeline.py
 M app/domain/enums.py
 M app/domain/exceptions.py
 M app/domain/interfaces/business_context_repository.py
 M app/domain/interfaces/persistence_unit_of_work.py
 M app/infrastructure/storage/models.py
 M app/infrastructure/storage/repositories/business_context.py
 M app/infrastructure/storage/unit_of_work.py
 M app/main.py
 M docs/decisions/README.md
 M docs/roadmap/README.md
 M frontend/src/App.tsx
 M frontend/src/api/client.ts
 M frontend/src/api/contexts.ts
 M frontend/src/api/errors.ts
 M frontend/src/components/AppShell.tsx
 M frontend/src/components/contexts/copy.ts
 M frontend/src/components/mailbox/AttachmentAnalysisPanel.tsx
 M frontend/src/components/mailbox/AttachmentItem.tsx
 M frontend/src/components/mailbox/AttachmentsSection.tsx
 M frontend/src/components/mailbox/MessageAnalysisSection.tsx
 M frontend/src/hooks/useContexts.ts
 M frontend/src/index.css
 M frontend/src/pages/ContextWorkspacePage.tsx
 M frontend/src/pages/MailboxWorkspacePage.tsx
 M frontend/src/test/mailboxAnalysis.test.tsx
 M frontend/src/test/mailboxAttachments.test.tsx
 M frontend/src/test/workflowReview.test.tsx
 M tests/integration/test_cors.py
 M tests/postgres/alembic_checks.py
 M tests/postgres/conftest.py
 M tests/support/in_memory_persistence.py
 M tests/unit/infrastructure/storage/test_alembic.py
 M tests/unit/infrastructure/storage/test_models.py
 M tests/unit/infrastructure/storage/test_phase21d_migration.py
?? AGENTS.md
?? alembic/versions/22b0001_business_work_items.py
?? app/api/routes/work_items.py
?? app/application/services/work_item_provenance.py
?? app/application/services/work_items.py
?? app/domain/interfaces/business_work_item_repository.py
?? app/domain/models/business_work_item.py
?? app/domain/models/business_work_item_event.py
?? app/domain/models/business_work_item_source.py
?? app/domain/models/context_timeline.py
?? app/domain/models/work_item_due.py
?? app/domain/models/work_item_intent.py
?? app/domain/models/work_item_provenance.py
?? app/domain/models/work_item_query.py
?? app/infrastructure/storage/repositories/business_work_item.py
?? app/infrastructure/storage/repositories/context_timeline.py
?? app/schemas/work_items.py
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/codex/reports/phase_22b_report.md
?? docs/codex/reports/phase_22c_report.md
?? docs/codex/reports/phase_22d_report.md
?? docs/codex/reports/phase_22e_report.md
?? docs/codex/reports/phase_22f_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
?? frontend/src/api/workItems.ts
?? frontend/src/components/workItems/CandidatePanel.tsx
?? frontend/src/components/workItems/ContextPicker.tsx
?? frontend/src/components/workItems/WorkError.tsx
?? frontend/src/components/workItems/WorkForm.tsx
?? frontend/src/components/workItems/creationDrafts.ts
?? frontend/src/hooks/useWorkItems.ts
?? frontend/src/lib/workItemDue.ts
?? frontend/src/pages/WorkItemDetailPage.tsx
?? frontend/src/pages/WorkItemsListPage.tsx
?? frontend/src/test/workItemDue.test.ts
?? frontend/src/test/workItems.test.tsx
?? tests/integration/test_work_item_conversion.py
?? tests/integration/test_work_items.py
?? tests/postgres/test_business_work_item_repository.py
?? tests/postgres/test_context_tracking_timeline.py
?? tests/postgres/test_work_item_conversion.py
?? tests/postgres/test_work_item_hardening.py
?? tests/postgres/test_work_item_queries.py
?? tests/unit/application/test_work_items.py
?? tests/unit/domain/test_business_work_item.py
?? tests/unit/infrastructure/storage/test_business_work_item_repository.py
?? tests/unit/infrastructure/storage/test_context_tracking_timeline.py
?? tests/unit/infrastructure/storage/test_phase22b_migration.py
?? tests/unit/infrastructure/storage/test_work_item_conversion.py
?? tests/unit/infrastructure/storage/test_work_item_queries.py
```
