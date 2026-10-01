# Phase 22E — Frontend & Business Context Timeline Integration

**Verdict: PASS — Phase 22E implementation and required local validation are complete.** Date: 2026-09-27.

## Authorization, interruption and verified baseline

The operator authorized Phase 22E implementation and safe local validation only, then explicitly requested continuation after a usage-limit interruption. The continuation inspected the actual partial files and recovered logs rather than restarting Phase 22. In particular, `ContextPicker.tsx` was present, syntactically complete and already wired into both work-item forms and list filtering; its pagination and recovery behavior received additional focused coverage. Phase 22F has not started.

Initial and resumed branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index empty. Repository Alembic head: **22b0001**. Read AGENTS.md, ADR-030, the roadmap, Phase 22A–D reports, the original Phase 22E instructions and the continuation instructions. Inspected the existing backend ownership/provenance/event contracts and React client, authentication, queries, navigation, mailbox/attachment/tabular panels, contexts, errors and confirmation dialog.

The initial worktree inventory is reproduced below. `.phase22e-baseline.log` records SHA-256 hashes for all 49 prior modified/untracked files; `.phase22e-status.log` records the original complete status. Of those 49 files, 46 remain byte-for-byte identical. Three receive only necessary Phase 22E extensions: `app/domain/enums.py` adds the timeline event enum; `app/main.py` exposes the existing Location response header to already-allowed browser origins; `tests/support/in_memory_persistence.py` supplies an empty context-event read for legacy in-memory timeline fixtures. Their Phase 22B–D changes remain intact. AGENTS.md remains byte-for-byte unchanged, SHA-256 `1160a91739c6030b5cd3c2cc03c4d1b44ff1ac7039b473523963ef27c14813d7`.

No reset, clean, stash, staging, commit or push occurred. No architectural contradiction requiring an ADR change was found. ADR-030 and migration `22b0001` are unchanged.

## Implementation inventory

Created:

- `app/domain/models/context_timeline.py`
- `app/infrastructure/storage/repositories/context_timeline.py`
- `docs/codex/reports/phase_22e_report.md`
- `frontend/src/api/workItems.ts`
- `frontend/src/components/workItems/CandidatePanel.tsx`
- `frontend/src/components/workItems/ContextPicker.tsx`
- `frontend/src/components/workItems/WorkError.tsx`
- `frontend/src/components/workItems/WorkForm.tsx`
- `frontend/src/components/workItems/creationDrafts.ts`
- `frontend/src/hooks/useWorkItems.ts`
- `frontend/src/lib/workItemDue.ts`
- `frontend/src/pages/WorkItemDetailPage.tsx`
- `frontend/src/pages/WorkItemsListPage.tsx`
- `frontend/src/test/workItemDue.test.ts`
- `frontend/src/test/workItems.test.tsx`
- `tests/postgres/test_context_tracking_timeline.py`
- `tests/unit/infrastructure/storage/test_context_tracking_timeline.py`

Modified:

- `app/application/services/context_timeline.py`
- `app/domain/enums.py`
- `app/main.py`
- `app/domain/interfaces/business_context_repository.py`
- `app/infrastructure/storage/repositories/business_context.py`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/contexts.ts`
- `frontend/src/api/errors.ts`
- `frontend/src/components/AppShell.tsx`
- `frontend/src/components/contexts/copy.ts`
- `frontend/src/components/mailbox/AttachmentAnalysisPanel.tsx`
- `frontend/src/components/mailbox/AttachmentItem.tsx`
- `frontend/src/components/mailbox/AttachmentsSection.tsx`
- `frontend/src/components/mailbox/MessageAnalysisSection.tsx`
- `frontend/src/hooks/useContexts.ts`
- `frontend/src/index.css`
- `frontend/src/pages/ContextWorkspacePage.tsx`
- `frontend/src/pages/MailboxWorkspacePage.tsx`
- `tests/support/in_memory_persistence.py`
- `tests/integration/test_cors.py`


## Browser tracking and API integration

`/tracking` provides the global owned list and explicit manual creation; `/tracking/:itemId` provides detail, editor, sources and paginated event history. Navigation and both pages require application authentication and `communications:analyze`. Manual creation works without a mailbox. The existing EciApiClient, MSAL token provider, React Query, Button and ConfirmDialog are reused. No new dependencies or IdP scopes were added.

The list submits filters to GET `/api/v1/work-items`: kind, status, archive visibility, direct context or unassociated, due mode, separate date/aware-timestamp ranges, overdue and supported sort. Pages default to 20, permit 50/100, and use limit/offset; no total is invented. Due sorting is offered only with an explicit date or timed mode. Loading, empty, safe error and retry states are included. Context selection is itself paginated at 20 and retains an already selected value outside the current page. Archived contexts are available as list filters; creation/association selection requests active contexts.

Manual and conversion forms submit only on the final Create/Confirm action. A client-generated creation key is retained with the exact submitted fields after uncertain failure. Fields are locked while replaying that request; closing and reopening resumes it from memory in the same authenticated application session. Pending candidate confirmation also retains its original reviewed observation and locator, so the original request can be replayed after closing even if the persisted source has disappeared. No automatic key replacement permits a silent duplicate. Definite validation/authorization/missing-source rejections and a confirmed archived-context rejection allow correction with the same key. A changed-key-payload conflict remains visible and requires recovery of the original intended request. Both 200 replay and 201 creation succeed without claiming another transition was recorded. Drafts, candidate text and sources are not written to browser storage.

PATCH uses an editor snapshot and `expected_version`; a background refresh cannot advance that snapshot's version and silently overwrite another change. Description/due can be cleared and context can be attached, detached or moved. Kind, origin, owner, sources and journal remain immutable. Stale versions expose explicit reload/review recovery. Lifecycle confirmation captures the displayed version, with Open, In progress, Complete, Cancel, Reopen, Archive and Restore actions appropriate to the current state. Terminal items require reopening before editing; archived items permit restoration only. No-op statuses are not offered as new transitions. Completion is described as a human declaration, not independent fulfillment verification. Tracking contains no Send or Execute controls.

## Due values and timezone review

Due mode must be explicitly reviewed: none, date-only or timed. Date-only values are calendar strings throughout; calendar validation does not construct JavaScript Date or UTC-midnight values. The exact YYYY-MM-DD and confirmed IANA zone are submitted. Browser timezone is an editable suggestion and requires a confirmation checkbox.

Timed inputs are local wall times. Candidate offsets are enumerated and round-tripped through the named zone. No valid round-trip rejects a DST gap; multiple valid offsets require a deliberate selection. The final value is aware RFC 3339 with the chosen offset and zone. Saved values render in their confirmed timezone, including the actual offset to distinguish repeated wall times. Overdue presentation uses the backend result. No scheduler, reminder or automatic status change was added.

## Analysis confirmation, provenance and availability

Persisted communication analyses and both ordinary and XLSX attachment analyses expose Review tracking candidates only when a persisted ID exists. Candidate reads use the Phase 22D endpoint; selection, display, cancel and close perform no tracking write. The final reviewed request sends the exact server locator and `confirmed=true`. No edited display value is used to recompute a digest.

The full original observation, source classification, advisory notice, truncation, warnings and limitations remain visible. Reviewed title is independently entered and limited to 200 characters; 201–300-character XLSX source observations retain their full meaning in the display. Kind and due mode are explicit. Action and date observations are independent; amounts are not introduced as candidates and no date/action pairing occurs.

Detail displays retained bounded source references and persisted-metadata availability. The UI explains that provider content is not verified and that unavailable sources do not invalidate a saved item. Missing source, changed candidate, exact-candidate duplicate, creation-key/version conflicts and missing capability have non-sensitive messages. An authorized duplicate Location is accepted only if it matches the relative `/api/v1/work-items/<uuid>` path, then converted to an internal Tracking link. Arbitrary external URLs are rejected. CORS exposes only the Location response header to already-configured origins so cross-origin browsers can actually read the duplicate reference; origin allowlists, credentials and authorization policies are unchanged. An HTTP regression exercises the real conflict handler through CORS. Tracking reads and candidate review trigger no Analyze, mailbox retrieval, attachment bytes, parser/scanner, AI provider, workflow execution or send.

## Business Context and genuine timeline history

The Context workspace has a Tracking tab that requests current direct association through the work-item context filter. It does not infer membership from linked communications. Context archive does not mutate work-item lifecycle. Existing associated work items retain their independent editing/lifecycle rules; new archived-context associations are rejected by the backend, with correction available in the form. Tracking mutations invalidate all tracking lists/details and context queries, covering both the previous and next contexts.

The context timeline includes only committed work-item journal entries, with `work_item_event:<event_uuid>` identities and stored `occurred_at`. Titles are generic historical descriptions, with a link to the owned current item. No current title is represented as a historical snapshot. Due dates, updated_at and old analysis creation do not invent work-item events. A→B moves retain earlier events and detachment under A, record association under B, and put subsequent events under B. The current Tracking tab follows the current association, independently of those historical memberships.

## Focused SQL query improvement and pagination

The production SQLAlchemy context repository now projects only timeline columns from scoped durable records, combines them with UNION ALL and applies one merged `occurred_at DESC, id ASC` order and limit/offset. Analysis, attachment and workflow categories use owned context-link EXISTS predicates. Work-item events filter `user_id` and `context_at_event_id`, using the schema's existing access path. No owner-wide analysis payload, reply body or work-item source collection is materialized. The context ownership lookup remains in the service before projection. Legacy in-memory test adapters retain the portable assembly path; the production SQL path does not use it.

This is a focused read-query correction, not a context-history redesign or backfill. No category is independently truncated, so pagination does not omit valid merged entries. PostgreSQL locale collation initially exposed a real equal-time ordering mismatch with the pre-existing Python ordering; explicit PostgreSQL C / SQLite BINARY ID collation fixes it. SQLite UUID output is normalized to the established public form.

Tests cover all categories together, ties across boundaries at page sizes 1/7/20/100, genuine timestamps, context moves/detachment, current title independence and foreign-user/Platform Owner isolation. The representative query test includes 250 associated work-item events, 30 foreign events and 500 unrelated owner analyses. The page at offset 200 returns exactly 20 entries through one SELECT, with no payload columns. PostgreSQL EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) metrics are recorded in JUnit properties. Recovered focused evidence: **0.782 ms execution, 0.869 ms planning, 20 returned rows**. These are local synthetic measurements, not production throughput guarantees. Offset pagination is deterministic for unchanged data; it is not a snapshot across concurrent requests, and deep offsets still require database work.

## Authentication, cache isolation and accessibility

A keyed authenticated application tree owns a fresh QueryClient and memory-only creation recovery map for each application identity/authentication state. Unmount cancels requests, clears the prior cache and clears recovery state. Tracking query keys include application identity. AbortSignal passes through candidate/list/detail/event requests; pending writes are aborted on identity change/unmount and late results are checked before success callbacks. A previous identity's response cannot populate the new QueryClient. Context caches share that isolation. Mailbox-specific analysis panels reset by mailbox and persisted source identity. No mailbox identifier becomes an authorization key; backend ownership remains authoritative.

Forms have labels, required/disabled states, error announcements, initial editor focus and responsive grids. Existing modal confirmations provide focus trapping, keyboard cancel and restoration. Lifecycle mutations require explicit confirmation. Focused tests exercise dialog focus and manual-form axe checks; repository-wide dialog/accessibility regressions are included in the full frontend suite. No claim of a live-cloud or manual browser visual audit is made.

## Validation evidence and recovery

Recovered from actual log/JUnit files after the operator-reported usage-limit interruption:

- Focused backend/timeline: 49 passed, 0 failed/errors/skipped, 15.95 seconds.
- Complete guarded PostgreSQL: 209 passed, 0 failed/errors/skipped, 16.88 seconds.
- Focused frontend at continuation: 47 passed; then 49 passed after ContextPicker recovery/offset checks and 50 passed after closed-confirmation recovery coverage.
- An earlier complete frontend run had 394 passing tests. It predates the final additions and is superseded by the final run below.
- Typecheck/lint/ruff/pip/whitespace/Alembic checks were recovered and rerun as applicable; no count is inferred solely from a zero exit code.

The local diagnostic runner `.phase22e-local-tests.log` obtains disposable-container configuration internally, verifies the exact running `eci-phase22b-postgres` / `postgres:16` identity, loopback 5435 mapping and database `eci_test`, preserves the existing safety guard, and checks SQL current_database(), PostgreSQL major version and schema revision 22b0001 before each invocation. It does not rely on inherited database environment variables, print credentials or persist a connection string. Sandbox Docker access was denied; approved local execution used the same guarded target. PostgreSQL tests do not substitute SQLite or unknown/cloud infrastructure.

Intermediate failures were resolved: SQLite transaction BEGIN was excluded from SELECT-count measurement; PostgreSQL collation was corrected as described above; EXPLAIN measurement was corrected to avoid parsing literal workflow suffixes as SQLAlchemy bind names; frontend test selectors/types and the axe assertion were corrected. Final review additionally corrected archived-context creation recovery, visible timed offsets, authentication-state cache reset and CORS Location visibility. These failed/intermediate runs are not reported as passing gates.

Final executed results (overlapping suites are not additive):

| Gate | Passed | Failed | Errors | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Focused backend/timeline/CORS | 57 | 0 | 0 | 0 | 15.22 s |
| Complete guarded PostgreSQL | 209 | 0 | 0 | 0 | 14.93 s |
| Complete backend regression | 3127 | 0 | 0 | 0 | 217.18 s |
| Focused frontend | 50 | 0 | 0 | 0 | 7.26 s |
| Complete frontend (32 files) | 419 | 0 | 0 | 0 | 25.87 s |

- `npm run typecheck`: PASS.
- `npm run lint`: PASS.
- `npm run test -- --run`: PASS, 419 tests.
- `npm run build`: PASS; Vite reports the main 694.82 kB JavaScript chunk warning (193.14 kB gzip). No build errors.
- `python -m ruff check .`: PASS.
- `python -m pip check`: PASS, no broken requirements; only the non-writable pip-cache warning.
- `git diff --check`: PASS; untracked text files also checked for trailing whitespace/conflict markers.
- `python -m alembic heads`: PASS, sole head `22b0001`.

The final complete backend run includes all 209 real PostgreSQL tests and the CORS fix: **3,127 passed, 0 failures, 0 errors, 0 skipped**. It supersedes the earlier 3,126-test continuation run made before the final CORS regression. Phase 22E adds 15 backend tests (seven portable timeline cases, the same seven PostgreSQL cases and one CORS case), plus 50 frontend tests. The original Phase 22D counts are not used as fresh evidence.

Local reproduction commands actually executed:

```sh
python .phase22e-local-tests.log focused
python .phase22e-local-tests.log postgres
python .phase22e-local-tests.log full
npm run typecheck --prefix frontend
npm run lint --prefix frontend
npm run test --prefix frontend -- --run
npm run build --prefix frontend
python -m ruff check .
python -m pip check
git diff --check
python -m alembic heads
```

JUnit evidence: `.phase22e-focused.junit.log`, `.phase22e-postgres.junit.log`, `.phase22e-full.junit.log`. Frontend evidence: `.phase22e-frontend-focused.log`, `.phase22e-frontend-full.log`, `.phase22e-frontend-build.log`. Diagnostic files are local ignored artifacts, not staged repository changes. No required check remains blocked.


## Boundaries, limitations and exact next step

No new or modified migration. Alembic head remains **22b0001**. Cloud resources touched: **none**. No Azure/AWS access, deployment, cloud migration, IAM/secret/infrastructure operation, paid provider call, live mailbox/attachment retrieval, scanning/parsing through tracking, send, staging, commit or push.

Recovery state is intentionally memory-only: a full browser reload/sign-out clears it. After an uncertain creation followed by a full reload, inspect existing tracking before submitting a new intended item. The production build emits a non-failing warning for the main JavaScript chunk exceeding 500 kB; bundling redesign was not introduced. Browser and server timezone databases may differ; the backend remains authoritative and rejects invalid/mismatched values. Historical sub-minute timezone offsets fail closed in the minute-offset picker. Source availability describes retained metadata, not live mailbox content. Completion remains user-declared. Existing context archive/restore history remains limited to the prior public contract. No unresolved ADR deviation is intended.

**PASS.** All Phase 22E deliverables and required local validation gates are complete. No known failing test or unresolved implementation defect remains. The limitations above describe evidence/scope boundaries, not cloud or Phase 22F acceptance. No Phase 22F work was started.

Recommended exact next step, requiring new operator authorization: **Implement Phase 22F local hardening and release-readiness only under ADR-030, using this Phase 22E report and the preserved worktree; run the roadmap's security/concurrency/timezone/performance/migration/accessibility gates locally, without cloud access, staging, commit, push or Phase 22G.** This recommendation is not execution authorization. Stop after Phase 22E.

## Initial complete working-tree inventory

```text
 M app/api/dependencies.py
 M app/api/router.py
 M app/domain/enums.py
 M app/domain/exceptions.py
 M app/domain/interfaces/persistence_unit_of_work.py
 M app/infrastructure/storage/models.py
 M app/infrastructure/storage/unit_of_work.py
 M app/main.py
 M docs/decisions/README.md
 M docs/roadmap/README.md
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
?? app/domain/models/work_item_due.py
?? app/domain/models/work_item_intent.py
?? app/domain/models/work_item_provenance.py
?? app/domain/models/work_item_query.py
?? app/infrastructure/storage/repositories/business_work_item.py
?? app/schemas/work_items.py
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/codex/reports/phase_22b_report.md
?? docs/codex/reports/phase_22c_report.md
?? docs/codex/reports/phase_22d_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
?? tests/integration/test_work_item_conversion.py
?? tests/integration/test_work_items.py
?? tests/postgres/test_business_work_item_repository.py
?? tests/postgres/test_work_item_conversion.py
?? tests/postgres/test_work_item_queries.py
?? tests/unit/application/test_work_items.py
?? tests/unit/domain/test_business_work_item.py
?? tests/unit/infrastructure/storage/test_business_work_item_repository.py
?? tests/unit/infrastructure/storage/test_phase22b_migration.py
?? tests/unit/infrastructure/storage/test_work_item_conversion.py
?? tests/unit/infrastructure/storage/test_work_item_queries.py
```

## Final branch, HEAD and complete working-tree inventory

Branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index empty; all Phase 22 work remains uncommitted.

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
