# Phase 22 — Action, Deadline & Obligation Tracking

## Closure status addendum — 2026-10-02

**Implementation complete; local validation complete; AWS scoped deployment/browser validation complete; Azure backend/lifecycle/frontend/browser validation complete; source committed and pushed to master; CI passed.**

Final implementation commit: **`46128f261857cfe041c1caadcc679452d03b0967`** (`46128f2`), `feat: add Phase 22 action and obligation tracking`. Local `HEAD`, `master` and `origin/master` match. The operator reported successful push and CI workflow **PASS**, run **`36846483687`** (`master`, `push`); no remote checks were repeated for this documentation update.

| Evidence category | Completed scope and source |
|---|---|
| Local | Implementation and regression complete; [Phase 22F](../codex/reports/phase_22f_report.md), historical results not rerun |
| AWS operator-observed | Migration/backend, controlled lifecycle, frontend and scoped browser validation complete; [AWS report](../codex/reports/phase_22g_report.md#closure-addendum--2026-10-02) preserves outstanding acceptance limits |
| Azure operator-observed | Backend deployed; schema `22b0001` verified; W1–W8, frontend deployment and scoped browser acceptance passed; [Azure evidence](../codex/reports/phase_22h_azure_readiness_report.md#closure-addendum--2026-10-02) |
| CI | Operator-reported passing push workflow for the implementation commit above; separate from local/cloud evidence |

Azure fixture `7acbfa6a-6480-46d3-93b5-a83b661ef184` remains cancelled/restored (unarchived), version 7, with exactly seven events and zero sources. Both ignored readiness directories remain local deployment/rollback evidence, outside source-controlled runtime content.

Mailbox attachment regression was not revalidated in this closure; production-scale load/recovery, PITR rehearsal and full disaster recovery were not tested. Historical reports retain their original limitations. These scoped results do not establish unconditional production readiness or completion of every original live acceptance criterion.

The original authority/status table, planned slices and recommended next action below are retained as the architecture-lock record; they are not current pending implementation instructions. No next phase is started by this update.

## Authority and status

[ADR-030](../decisions/ADR-030-action-deadline-and-obligation-tracking.md) is the accepted architecture contract. All six B1–B6 recommendations from the [readiness assessment](../codex/reports/phase_22_readiness_assessment.md) were explicitly approved by the operator. The [22A report](../codex/reports/phase_22a_report.md) records documentation verification. The readiness report remains unchanged historical evidence.

| Slice | Status / acceptance category |
|---|---|
| 22A — Architecture and product decision lock | PASS — documentation only |
| 22B — Domain, persistence and atomic event-history foundation | Planned; requires explicit authorization |
| 22C — Manual tracking API and ownership | Planned; requires explicit authorization |
| 22D — Verified provenance and human-confirmed analysis conversion | Planned; requires explicit authorization |
| 22E — Frontend and Business Context timeline integration | Planned; requires explicit authorization |
| 22F — Local hardening and release readiness | Planned; local runtime release gate |
| 22G — Separately authorized Azure/AWS validation and closure | Planned; independent per-cloud authorization and evidence |

Phase 22 is not implemented or closed. Phase 20 and Phase 21 remain CLOSED / PASS. Phase 17D remains deferred. No historical test/cloud result certifies Phase 22 runtime behavior. Phase 22A acceptance is not permission to implement 22B or execute any migration.

## Approved product and architecture

| Decision | Delivery contract |
|---|---|
| B1 | Separate `BusinessWorkItem`, immutable `action/obligation`, one lifecycle, optional single due value and direct context, bounded sources, single-user ownership; `WorkflowAction` unchanged |
| B2 | `none/date/datetime` typed due modes, confirmed IANA zone, DST validation, computed overdue; open/in_progress/completed/cancelled, explicit reopen, separate archive/restore |
| B3 | Authenticated `communications:analyze`; also `communications:read` on mailbox-backed creation/confirmation; verified `(iss, sub)` → `users.id`; no owner bypass or new scope |
| B4 | Explicit manual or persisted-analysis confirmation, deterministic candidate projection, server-reloaded owned sources, lifetime creation keys and exact origin-candidate uniqueness; no provider change |
| B5 | Optional owner-verified context, expected-version mutations, atomic minimal append-only events with real context-at-event, explicit moves and archived-context rules |
| B6 | Reversible archive, no public hard delete, account-erasure cascades; global Tracking UI, conversion, context Tracking tab and genuine history; no automation |

The API namespace is `/api/v1/work-items`. The ADR locks request/response shapes, permissions, filters, error semantics and concurrency. `/api/v1/workflow-actions` is separate. One planned revision `22b0001` revises actual repository head `21d0001` and creates **business_work_items, business_work_item_sources and business_work_item_events**, with all confirmation, source, digest, version and history fields. **No 22D migration is planned.** Recheck head and revision availability before implementation; a conflicting baseline requires review, not editing applied migrations.

First release includes global list, manual creation, detail/editor, due controls/filters, status/archive, explicit analysis conversion, optional context association, context Tracking tab and real event-history/timeline integration. Human-marked completion is not proof of legal fulfillment.

Common exclusions: team assignment/sharing, recurrence, standalone milestones, parent-child graphs, multiple deadlines, reminders/notifications, calendar/external synchronization, escalation, automatic tracking/compliance, automatic reply/Send/workflow linking or completion, new extraction/provider capabilities and Phase 17D. Every slice inherits these exclusions and all ADR security invariants.

## 22A — Architecture and product decision lock

- **Objective:** Convert approved B1–B6 into an accepted, implementation-ready contract.
- **Approved scope:** ADR-030, this roadmap, 22A report and necessary decision/roadmap indexes. Preserve existing readiness assessment and AGENTS.md.
- **Dependencies:** Verified `master` at `bfc68b0`, full assessment, ADR-029 and Phase 20/21 contracts; explicit operator decision approval.
- **Files:** `docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md`, `docs/roadmap/phase-22-action-deadline-obligation-tracking.md`, `docs/codex/reports/phase_22a_report.md`, the two directory README indexes.
- **Migration implications:** None executed/created; lock all three tables and fields to proposed `22b0001 → 21d0001`; none deferred to 22D.
- **Security invariants:** Record identity/owner separation, no AI authority, no content retrieval, no send/approval bypass and no cloud authorization inheritance.
- **Acceptance:** B1–B6 settled; due/lifecycle/schema/source/retry/context/event/API contracts consistent; no remaining schema-affecting product choice; historical Phase 20/21 evidence untouched.
- **Required checks:** Markdown references/navigation, ADR numbering, cross-document consistency, decision coverage, preservation hashes, whitespace and exact working-tree inventory. No application/database tests.
- **Explicit non-goals:** Code, migrations, application tests, runtime verification, provider/mailbox/cloud operations.
- **Stop/authorization boundary:** Stop after report. Await explicit authorization for 22B; no commit/push authorization.

## 22B — Domain, persistence and atomic event-history foundation

- **Objective:** Establish the durable aggregate and transactional safety before exposing tracking operations.
- **Approved scope:** Domain enums, `BusinessWorkItem`, typed due/source/event values, lifecycle/edit/archive guards, immutable kind/owner/origin/keys, repository ports and SQLAlchemy persistence, expected-version writes, canonicalization/idempotency helpers, all three table models, atomic item/source/event unit of work. Internal foundation supports origin/source constraints; AI projection/confirmation orchestration remains 22D.
- **Dependencies:** Accepted 22A and explicit 22B authorization; confirm actual branch/head/worktree and migration numbering; verify any database tests target disposable local infrastructure before connecting.
- **Likely files/modules:** `app/domain/models/business_work_item.py`, `business_work_item_source.py`, `business_work_item_event.py`; enums/exceptions; domain repository and persistence-unit-of-work interfaces; `app/infrastructure/storage/models.py`, `repositories/business_work_item.py`, `unit_of_work.py`; bounded pure canonicalization helper; focused domain/storage tests and local PostgreSQL fixtures/head inventories; `docs/codex/reports/phase_22b_report.md`.
- **Migration implications:** Proposed `alembic/versions/22b0001_business_work_items.py`, parent `21d0001`, creates items/sources/events and all ADR constraints/indexes. All confirmation/candidate columns are included now. No legacy AI backfill. Downgrade refuses any populated tracking table before DDL. No cloud migration.
- **Security invariants:** Server owner, child composite ownership FKs, source/context ownership contract, minimal events, no content/provider/executor dependencies, user erasure cascades, safe conflict recovery.
- **Acceptance criteria:** SQLite/PostgreSQL round-trip and constraint parity; state/timestamp/due checks; genuine events atomic from first creation; version and creation-key races have one winner; failed writes leave zero residue; all tables survive source deletion independently; account erasure removes children; same-owner active context selection serialized with archive writes.
- **Required tests:** Focused domain/repository tests, date-only/DST/offset boundaries, invalid field combinations including SQL NULL behavior, child owner mismatch, concurrent versions/key uniqueness, event/source rollback, context-archive race, empty/populated downgrade, data-preserving upgrade from Phase 21 fixtures. Full backend when shared UoW changes; `ruff check .`, `pip check`, `git diff --check`. Keep local PostgreSQL safety helpers enabled.
- **Explicit non-goals:** Public APIs, candidate projection/confirmation service, frontend, AI calls, sends, cloud validation; schema readiness is not feature exposure.
- **Stop/authorization boundary:** Report changed files/revision/test counts/limitations and stop for explicit 22C authorization. No commit, push or deployment unless separately instructed.

## 22C — Manual tracking API and ownership

- **Objective:** Deliver owned manual tracking through the locked API without AI conversion.
- **Approved scope:** Manual source-free create, list/read/edit, typed due filters/overdue, status/reopen/archive/restore, event reads, explicit direct context attach/detach/move; creation replay and expected-version errors. Implement bounded queries and shared error codes. Reject nonempty sources until 22D.
- **Dependencies:** 22B accepted and explicit 22C authorization; use ADR request/permission contract.
- **Likely files/modules:** `app/application/services/business_work_items.py`, application exceptions; `app/schemas/work_items.py`, `app/api/routes/work_items.py`, router/dependencies/exception wiring; repository query methods; unit and API integration tests; API documentation and `phase_22c_report.md`.
- **Migration implications:** None planned; 22B already contains all fields/indexes. Any proven extra index requires a reviewed additive migration, not modifying applied 22B.
- **Security invariants:** Authenticated analyze even in disabled-auth mode; owner predicates on every item/context/filter/event; no Platform Owner exception; unknown fields cannot set actors/owners/timestamps; no external side effects.
- **Acceptance criteria:** Manual items work without mailbox/context; dates render and filter with correct timezone semantics; 404 for unknown/foreign objects; active/terminal/archive policy exact; no-op version rules honored; concurrent edits never overwrite; stale context selections fail safely; pagination/order correct.
- **Required tests:** AuthN/capability matrix, ordinary/Platform Owner cross-user cases, strict schemas and nested context IDs, malformed date/zone/DST, status/timestamp transitions, context archive/move races, idempotent create/lost-response retry, version conflicts, persistence failures, privacy-log sentinels. Spies prove no AI/mailbox/attachment/parser/scanner/executor calls. Focused then full backend for shared route/error changes, standard lint/dependency/whitespace checks.
- **Explicit non-goals:** Nonempty source creation, AI conversion/candidates, frontend, automated due transitions or reminders.
- **Stop/authorization boundary:** Report local evidence and stop before 22D. Runtime API acceptance does not authorize cloud deployment.

## 22D — Verified provenance and human-confirmed analysis conversion

- **Objective:** Convert user-reviewed existing observations into durable tracking with trustworthy provenance.
- **Approved scope:** Add typed source references to manual creation; read-only deterministic candidate projection and explicit `from-analysis` final confirmation for persisted communication/ordinary attachment/XLSX observations. Validate source type/locator/digest/owner, derive tuples, handle unavailable sources/replays and origin-candidate uniqueness. Sources stay immutable after creation.
- **Dependencies:** 22C accepted, explicit 22D authorization; unchanged persisted analysis/provider contracts and 22B source schema.
- **Likely files/modules:** `app/application/services/work_item_confirmation.py`, deterministic projection/canonicalization helpers, work-item service/schemas/routes and source repository methods; owned analysis/connector access through existing UoW; confirmation/source tests and `phase_22d_report.md`.
- **Migration implications:** **None planned.** All source/candidate/confirmation fields, unique constraints and indexes exist in 22B. Do not introduce `22d0001` merely to enable behavior or fabricate history for existing manual items.
- **Security invariants:** Analyze plus read for any mailbox-backed creation source, even nested manual references; reloaded owned persisted source; explicit final user gesture; no AI owner/date authority; no pairing of separate XLSX arrays; no bytes/network/provider/executor access.
- **Acceptance criteria:** View/select/cancel causes zero tracking writes; explicit confirmation atomically creates one item plus minimal verified sources/events; duplicate concurrent confirmations create one item; changed/deleted source before new create fails safely; same-key replay after deletion works with stored permission checks; source disappearance never deletes the confirmed item; direct-text analysis works with analyze only.
- **Required tests:** Permission/source-type confusion, foreign analyses/connectors/contexts, mailbox tuple tampering, invalid field/index/digest/projection version, repeated or new analysis IDs, same/new key races, payload conflict, source deletion/disconnect, at-most-ten sources, overlong text requiring explicit user editing, injection/truncation disclosure, atomic rollback, log privacy; PostgreSQL uniqueness tests and offline Phase 21/provider parity regressions. Standard backend checks as applicable.
- **Explicit non-goals:** Provider prompts/contracts, fresh extraction, automatic conversion, semantic duplicate merging, source editing, historical backfill, formula execution.
- **Stop/authorization boundary:** Report and stop before 22E; no live mailbox or paid provider validation implied.

## 22E — Frontend and Business Context timeline integration

- **Objective:** Make the complete first-release tracking flow usable and present genuine history.
- **Approved scope:** Global Tracking list and manual create; detail/editor, due/filter/status/archive controls; final-confirmation forms in persisted analysis panels; context association and Tracking tab; real item events in context timeline using owner/context-scoped queries. Preserve history through moves and use current association for current items. Focused query improvements are allowed where required to meet merged timeline acceptance, with evidence.
- **Dependencies:** 22C/D accepted and explicit 22E authorization; use established typed API/React Query/permission/error patterns.
- **Likely files/modules:** `frontend/src/api/workItems.ts`, client/hooks, tracking pages/components, `App.tsx` and navigation, existing mailbox analysis/tabular panels, `ContextWorkspacePage.tsx`, context types/hooks/errors; `app/application/services/context_timeline.py`, timeline enums/schemas/repository queries; frontend and backend timeline tests; `phase_22e_report.md`.
- **Migration implications:** None expected; 22B includes event indexes. Any measured additional index is separately reviewed and additive.
- **Security invariants:** No mutation on view/autosave/selection; no auto-Analyze/bytes/send; server ownership authoritative; identity-switch cancellation/cache reset/late-response isolation; no default browser persistence of drafts/source text.
- **Acceptance criteria:** Complete manual and confirmed flows; accessible keyboard/focus/error/loading/empty states; explicit date-only/zone and uncertainty/truncation displays; saved item remains usable with missing source; retry reuses creation key; stale edits recover without overwrite. Context A→B move keeps real A history, records B association now, and changes current Tracking membership. Timeline merges correctly without fabricated events or unbounded new owner-wide scans.
- **Required tests:** Vitest/React Testing Library manual/confirmation/cancel flows, permission gates, date-only and DST UI, archived/terminal guards, duplicate retry/conflict recovery, identity switch/late responses, invalidation of both old/new context views; timeline owner isolation, genuine timestamps, ties/pagination and representative-volume query behavior. Frontend typecheck, lint, full tests and production build; focused and full backend when shared timeline changes; ruff/pip/diff checks as appropriate.
- **Explicit non-goals:** Broad UI redesign, calendar/notifications, workflow execution controls inside tracking, legacy event backfill or complete context event sourcing.
- **Stop/authorization boundary:** Report feature evidence and query limitations; stop for 22F authorization.

## 22F — Local hardening and release readiness

- **Objective:** Establish local release evidence for the complete approved feature before any cloud work.
- **Approved scope:** Security/ownership/provider-side-effect regressions, concurrency/atomicity, representative query performance and timezone parity, privacy/error checks, safe local migration/rollback rehearsal, frontend accessibility/identity cache tests, API/runbook/documentation alignment; fix Phase 22 defects only.
- **Dependencies:** 22B–E accepted; explicit 22F authorization; disposable local test database verified before tests that migrate/truncate it.
- **Likely files/modules:** Phase 22 backend/frontend tests, PostgreSQL migration inventories/safety helpers, relevant implementation fixes, API/runbook/roadmap documentation and `phase_22f_report.md`; CI only if needed to cover new checks.
- **Migration implications:** Rehearse reviewed `21d0001 → 22b0001` and empty-table reverse path locally. Populated downgrade must refuse without data loss. No new feature migration expected; do not delete real history to force success.
- **Security invariants:** Full ADR threat boundaries, no forbidden content/AI/send side effects, no raw business payloads in logs, no weakening local DB safety checks.
- **Acceptance criteria:** Required local suites pass with exact counts; migration data preservation, parallel-request atomicity, account erasure, date-only/timezone filtering and bounded query behavior evidenced; no unresolved critical/high boundary defect. Produce reviewable artifact/deployment plan; distinguish local evidence from live claims.
- **Required tests/checks:** Focused then full backend, disposable local PostgreSQL integration and migration safety; `ruff check .`, `pip check`, `git diff --check`; frontend `npm run typecheck`, `npm run lint`, `npm run test -- --run`, `npm run build`. Provider tests remain Mock/stub/offline. Record failed/skipped checks and environment limits honestly.
- **Explicit non-goals:** Azure/AWS access, production migration, paid AI, live mailbox content, Phase 17D or new scope.
- **Stop/authorization boundary:** Stop at local release verdict; 22F PASS is not cloud/deployment/commit/push permission.

## 22G — Separately authorized Azure/AWS validation and closure

- **Objective:** Validate accepted artifacts independently in authorized cloud environments and close only evidenced scope.
- **Approved scope once separately authorized:** Use established runbooks to inspect actual environment/artifact/schema, apply approved changes only where needed, exercise approved tracking fixtures with authorized identities, record per-cloud behavior and evidence limits. Validate manual/confirmed tracking, due/status/archive/context/history and safe logs without requiring new AI calls or content retrieval.
- **Dependencies:** 22F PASS; explicit named Azure and/or AWS access/deployment/migration authorization, reviewed validation plan and rollback/retention plan. Phase 21 cloud authorization does not carry forward. If suitable persisted fixtures are absent, request an approved fixture plan rather than retrieve mailbox content implicitly.
- **Likely files/modules:** Established deployment/migration runbooks only if needed, `phase_22g_report.md`, roadmap and closure documentation; no new infrastructure presumed necessary.
- **Migration implications:** Verify actual live revision before applying reviewed chain independently per cloud; never blindly repeat a completed operation. Preserve prior analyses/tracking; no destructive populated rollback.
- **Security invariants:** No IAM expansion, secret change, resource stop/delete/resize/recreate, paid AI, mailbox/attachment retrieval or send without distinct explicit instruction. Tracking smoke tests should need none of these.
- **Acceptance criteria:** Per-cloud artifact identity, schema head, health and approved user flows verified; distinguish agent-observed and operator-reported evidence, local-only tests and untested live boundaries. Closure states exactly which authorized cloud gates passed or remain pending.
- **Required tests/checks:** Established live smoke/health/schema checks and approved isolation/due/history tests; safe log inspection. No inference that historical Phase 21 PASS proves Phase 22. Report cloud resources actually touched.
- **Explicit non-goals:** Infrastructure redesign, multi-cloud replication, automatic business workflows, Phase 17D or next-phase work.
- **Stop/authorization boundary:** Stop after authorized validation and report; closure does not authorize commit/push, resource shutdown or starting another phase.

## Recommended next action

Explicitly authorize **Phase 22B only**, with ADR-030 and this roadmap as the handoff. Prefer a fresh Codex session to keep the implementation/test budget and authorization boundary clear. Re-read AGENTS.md and recheck HEAD/worktree/migration head there, preserving the pre-existing assessment and all uncommitted documentation. Do not redo B1–B6 approval or begin 22C automatically.
