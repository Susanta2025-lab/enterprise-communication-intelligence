# Phase 22A — Architecture & Product Decision Lock

Assessment date: 2026-09-26. **Result: PASS — documentation-only architecture acceptance.**

All six operator-approved decisions B1–B6 are formally accepted in [ADR-030](../../decisions/ADR-030-action-deadline-and-obligation-tracking.md). The [Phase 22 roadmap](../../roadmap/phase-22-action-deadline-obligation-tracking.md) defines 22A–22G. **Phase 22B is architecturally ready, but implementation has not been authorized by this slice and has not begun.** No remaining technical blocker was found for beginning an explicitly authorized 22B on this baseline.

## Verified baseline and evidence boundary

- Branch: `master`; HEAD `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`, Phase 21 closure. Local status showed `master...origin/master`; no fetch/remote verification performed.
- Starting untracked files: `AGENTS.md` and `docs/codex/reports/phase_22_readiness_assessment.md`. Both preserved byte-for-byte. No pre-existing tracked changes.
- Read repository AGENTS.md; no nested docs AGENTS.md found. Read the full readiness assessment, ADR-029 and relevant Phase 20/21 roadmaps.
- Inspected domain ActionItem/WorkflowAction/BusinessContext, persisted analysis/attachment contracts, identity mapping, authenticated API dependencies and context/history routes, SQLAlchemy ownership/context writes and unit of work, current context timeline and typed frontend context contracts.
- Parsed migration revision declarations without importing application/Alembic runtime: 11 revisions, one head **`21d0001`**, parent `20c0001`. No PostgreSQL connection, Alembic execution or live database-head check.
- ADR-030 was unused before writing; no conflicting migration or material baseline change found.
- Phase 20 and Phase 21 remain CLOSED / PASS. Phase 17D remains deferred. Prior cloud/CI/test evidence was not rerun or upgraded into Phase 22 runtime evidence.

The [pre-existing readiness assessment](phase_22_readiness_assessment.md) remains historical, including its earlier statements that approvals were pending. The operator's subsequent explicit approval and ADR-030 resolve those conditions without rewriting that file.

## Approved decision inventory

| Group | Accepted architecture lock | Implementation consequence |
|---|---|---|
| B1 | Separate `BusinessWorkItem`, action/obligation, immutable kind, one lifecycle and optional due/context | New aggregate and tables; never extend reply `WorkflowAction` |
| B2 | None/date-only/datetime, confirmed IANA zone and DST validation, computed overdue, explicit reopen, archive independent of status | Typed due values and SQL null consistency; server timestamps; active-only edits; genuine prior transition history |
| B3 | Authenticated analyze, plus read for mailbox-backed creation/confirmation; internal user ownership everywhere | Existing capabilities/identity resolver; no new IdP scope or Platform Owner bypass |
| B4 | Manual or explicit persisted-analysis confirmation, deterministic locators, bounded provenance and lifetime retry/candidate uniqueness | Server reload/validation, atomic creation and safe unique-conflict recovery; no provider changes |
| B5 | Direct optional context, real minimal append-only events, context-at-event, expected versions | Versioned context moves, archived-context policy, atomic events and scoped timeline queries |
| B6 | Reversible archive, no public hard delete, account erasure preserved, complete Tracking UI delivery | Retained minimal history/sources; safe populated downgrade refusal; automation and expanded collaboration deferred |

These decisions are settled. New implementation defects or an actual contradictory baseline would require explicit reporting, not treating B1–B6 as unanswered questions.

## Architecture and ambiguities resolved

ADR-030 is the normative detailed schema/API contract. The roadmap specifies slice acceptance and stop boundaries.

| Former ambiguity | Locked resolution |
|---|---|
| Action versus obligation versus deadline | One immutable action/obligation kind; deadline is optional typed due information, not a third aggregate |
| Domain/SQL owner terminology | Domain `owner_user_id` maps to SQL `user_id`; never accepted from client |
| Date-only wire spelling | `due.kind=date` / SQL `due_kind=date`; calendar date plus confirmed zone, no artificial timestamp |
| Ambiguous local datetime | Require explicitly chosen valid RFC 3339 offset and zone round-trip; reject gaps/mismatches |
| Due filters and sorting | Separate inclusive date and instant ranges; due sort only within an explicit mode; per-zone overdue before pagination; no mixed fake-midnight sort |
| Reopening and archive | Terminal→open requires explicit reopen; terminal business edits require reopen; archived items restore before mutation; no-op still checks version |
| Mutation concurrency | Positive body `expected_version`; conditional owner/version write; one version increment per actual mutation; atomic event sequence |
| Context ownership FK | Existence FK with SET NULL; same-owner and active-target enforcement in the transaction using an owned row lock; no composite SET NULL affecting owner |
| Context archive versus progress | Existing linked items can progress/detach subject to item state; refuse new associations to archived contexts; archive has no cascade into tracking status |
| Context moves/history | Disassociate event under old context, associate under new, one timestamp/version with ordinals; prior history stays under its original context |
| Initial migration boundary | All three tables and all fields in 22B; no candidate/source columns deferred to 22D |
| Source bounds and editing | At most ten initial typed references; AI origin mandatory; no later source editing/merge API |
| Candidate contract | Projection v1 with typed persisted ID/field/index/digest; XLSX arrays separate; exact uniqueness applies to designated origin candidate |
| Creation hashing/retry | 1–128-character opaque client key, versioned canonical normalized intent, SHA-256; same payload replay 200, changed payload 409; lifetime retention |
| Source deletion and retries | Existing owned replay uses stored source permissions and survives deletion; new creation validates available owned source; no automatic reacquisition |
| Candidate read permission | Analyze-only read of persisted owned history; final mailbox-backed creation still requires read+analyze |
| Error shape | Existing ErrorResponse with optional codes; owned Location header for duplicate-candidate reference; no foreign-object disclosures |
| Journal scope | Minimal typed metadata, no prior title/description snapshots; append-only repository, account erasure exception; no event-sourced rewrite |
| ADR index wording | Accepted means approved architecture; implementation status explicit per ADR, so documentation acceptance does not imply delivered code |

Concrete contract examples are covered by the ADR: manual item without mailbox/context; direct-text analysis confirmation with analyze only; mailbox/XLSX confirmation with read+analyze; date-only due without UTC conversion; retry after source deletion; foreign item/source/context returning 404 even for Platform Owner; and context A→B retaining A's history. No newly discovered contradictory requirement prevents this lock.

## Migration design and revision boundaries

**No migration file was created or modified.** Actual repository head remains `21d0001`.

Proposed `22b0001` revises `21d0001` and creates:

1. `business_work_items`: owned root, immutable kind, text bounds, optional context FK, typed due fields/checks, lifecycle timestamps, archive, version, origin/confirmation fields, creation key/request hash and origin-candidate uniqueness.
2. `business_work_item_sources`: typed opaque analysis/communication references and candidate locators, canonical source key, bounded initial source set, composite parent/owner FK.
3. `business_work_item_events`: composite parent/owner FK, actor equality, genuine occurrence/context, resulting version/ordinal uniqueness, bounded typed metadata and owner/item/context history indexes.

All fields, constraints and indexes specified in ADR-030 exist in the initial 22B migration. **22D has no planned migration.** 22C/D/E use that schema; any measured new index requires an additive reviewed revision. Recheck actual head and proposed revision availability when 22B is authorized.

No historical AI backfill, no parallel analysis persistence and no modifications to existing analyses/workflows are planned. Sources/events cascade with items and items with account erasure; source deletion does not cascade into tracking. Downgrade refuses populated tracking tables before any DDL. Any exception needs a separately approved retention/export/rollback plan.

## API and permission matrix

Base namespace is **`/api/v1/work-items`**; existing `/api/v1/workflow-actions` stays unchanged. All rows/filters/events remain scoped to internal owner.

| Operation | Required permission | Additional condition |
|---|---|---|
| Manual POST root | Authenticated `communications:analyze` | Add `communications:read` for any mailbox-backed source; owned active context and verified references |
| POST `/from-analysis` | Authenticated analyze; read for mailbox-backed origin or additional source | Explicit final confirmation; reload owned persisted candidate/locator; no AI ownership/date authority |
| GET `/candidates` | Authenticated analyze | Owned persisted history only; no provider/content calls or writes |
| GET root / `/{id}` | Authenticated analyze | SQL owner predicates; referenced context filter verified as owned |
| PATCH `/{id}` | Authenticated analyze | Expected version, active/unarchived; new context owned and active |
| POST `/{id}/status` | Authenticated analyze | Expected version and allowed transition; explicit reopen |
| POST `/{id}/archive` / `/restore` | Authenticated analyze | Expected version and owned item |
| GET `/{id}/events` | Authenticated analyze | Owned item and owner-scoped events |
| Context Tracking tab / existing context timeline | Authenticated analyze | Owned context; current association for list, context-at-event for history |

No new IdP capability; no workflow approval/execution/Send permission inherited from tracking. Disabled-auth mode cannot open durable tracking APIs. Details, schema strictness, status codes, filters and pagination are locked in ADR-030.

## Remaining implementation risks and acceptance gates

These are future verification obligations, not unapproved product decisions or current technical blockers:

| Risk | Required evidence / slice |
|---|---|
| Partial item/source/event writes, unique races or aborted PostgreSQL transaction recovery | 22B/D local PostgreSQL rollback, key/candidate/version race and constraint tests |
| Context archive racing a new association | 22B/C transaction-lock test against existing context UPDATE behavior; no claim existing Phase 20 service already provides the new lock |
| Timezone/DST/date-only query drift across Python, PostgreSQL and browser | 22B/C/E validation and predicate/display parity; 22F unusual zone transitions |
| Existing timeline loads owner-wide analyses/workflows before sorting | 22E scoped new-event queries and measured merge/pagination behavior; focused query correction if needed; 22F volume evidence |
| Source type confusion or over-trusting advisory dates/owners | 22D owned-source reload, tuple/locator validation, no implicit creation, source-unavailable replay tests |
| Privacy leakage through validation, events or caches | 22C–F log sentinels, typed minimal metadata, identity-change/late-response tests |
| Account erasure and migration rollback data loss | 22B/F ORM/SQL cascade and populated-downgrade-refusal tests |

The context-lock and existing timeline-query details refine technical work already identified in the readiness assessment. They do not reopen accepted product scope. SQLite tests alone are insufficient evidence for PostgreSQL concurrency. Cloud validation is separate and independently authorized after local readiness.

## Documentation inventory

Created:

- [ADR-030](../../decisions/ADR-030-action-deadline-and-obligation-tracking.md)
- [Phase 22 roadmap](../../roadmap/phase-22-action-deadline-obligation-tracking.md)
- This report: `docs/codex/reports/phase_22a_report.md`

Modified:

- [Decision index](../../decisions/README.md): ADR-030 entry/summary and accepted-status meaning clarified to distinguish architecture from implementation.
- [Roadmap index](../../roadmap/README.md): Phase 22 navigation and documentation-only 22A status.

Preserved: pre-existing AGENTS.md and readiness report, ADR-029, Phase 20/21 roadmaps and closure evidence, application/frontend/backend code, migrations and application tests. No other files are part of this change.

## Verification results

Documentation checks only; application tests run **0**. No database checks, migrations, PostgreSQL connection, cloud access, paid provider call, mailbox/attachment retrieval, deploy, commit or push occurred. Cloud resources touched: **none**.

- Local Markdown references/navigation: **97 local links passed** across the five changed documents, including target existence and anchors where present.
- ADR numbering: ADR-030 available before creation; exactly one ADR-030 afterward, **30 unique numbered ADRs**, no duplicate numbered ADRs.
- Consistency: all B1–B6 represented in ADR, roadmap and report; same API namespace, all-three-tables-in-22B boundary, no planned 22D migration, owner/confirmation/archive/context rules and stop boundaries.
- `git diff --check`: passed. New untracked documents additionally checked for trailing whitespace/conflict markers because ordinary git diff omits them.
- Exact change inventory: three new Phase 22A documents and two modified documentation indexes; no changes to implementation, migrations or tests.
- Preservation SHA-256: AGENTS.md `1160a91739c6030b5cd3c2cc03c4d1b44ff1ac7039b473523963ef27c14813d7`; readiness assessment `12f6a5ce220f6e9c8e4bf364bac12958d8c0bc5b079dda2f16e2f2d7a3770cf2`, unchanged from pre-edit reads.

Final working-tree inventory (no staging/commit):

```text
 M docs/decisions/README.md
 M docs/roadmap/README.md
?? AGENTS.md
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
```

## Readiness and exact next action

**22A PASS. Phase 22B READY for explicit authorization; no remaining technical blocker identified.** Runtime correctness, performance and migration safety have not been certified by documentation checks.

Recommended operator instruction for a **fresh Codex session**:

> Implement Phase 22B only under ADR-030 and the Phase 22 roadmap: domain, persistence and atomic event-history foundation, with all three tables and all specified fields in proposed revision 22b0001 descending from verified head 21d0001. Recheck AGENTS.md, branch/HEAD/worktree and revision availability, preserve existing local documentation, and validate only against safe local test infrastructure. Do not start 22C, access clouds or paid providers, retrieve mailbox/attachment content, commit or push. Report evidence and stop after 22B.

A fresh session is recommended for implementation/test capacity and a clear scope boundary, not because B1–B6 need reconsideration. This report is a handoff, not permission to execute that next instruction. **Stop after Phase 22A.**
