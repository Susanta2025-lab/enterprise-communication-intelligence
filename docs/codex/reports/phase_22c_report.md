# Phase 22C — Manual Tracking API & Ownership

Date: 2026-09-26. Scope: implementation and LOCAL validation of Phase 22C only.

## 1. Baseline and preservation

Branch `master`; HEAD `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index empty at entry. Read AGENTS.md, ADR-030, Phase 22 roadmap and 22A/22B reports; inspected the domain, typed due values, canonical intent, journal, repository, UoW, authentication/identity, permissions, errors, contexts and migration. Repository head confirmed using `python -m alembic heads`: **22b0001**. No material contradiction with ADR-030 found.

The operator-reported Phase 22B results were treated as prior evidence: 93 new PostgreSQL tests, 187 complete PostgreSQL tests and 2,950 full regression passes. This phase independently executed local PostgreSQL tests, as recorded below.

Starting complete working-tree inventory:

```text
 M app/domain/enums.py
 M app/domain/exceptions.py
 M app/domain/interfaces/persistence_unit_of_work.py
 M app/infrastructure/storage/models.py
 M app/infrastructure/storage/unit_of_work.py
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
?? app/domain/interfaces/business_work_item_repository.py
?? app/domain/models/business_work_item.py
?? app/domain/models/business_work_item_event.py
?? app/domain/models/business_work_item_source.py
?? app/domain/models/work_item_due.py
?? app/domain/models/work_item_intent.py
?? app/infrastructure/storage/repositories/business_work_item.py
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/codex/reports/phase_22b_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
?? tests/postgres/test_business_work_item_repository.py
?? tests/unit/domain/test_business_work_item.py
?? tests/unit/infrastructure/storage/test_business_work_item_repository.py
?? tests/unit/infrastructure/storage/test_phase22b_migration.py
```

Preservation checks compare SHA-256 values captured at entry for every pre-existing modified/untracked file. Only the existing tracking repository interface and SQLAlchemy implementation were extended, to add list queries. All other baseline files remain byte-for-byte unchanged, including untracked AGENTS.md, all prior reports, ADRs, roadmaps, migration 22b0001 and Phase 22B tests. Nothing was reset, stashed, removed, staged, committed or pushed.

## 2. Exact Phase 22C file inventory

Added:

- `app/api/routes/work_items.py`
- `app/application/services/work_items.py`
- `app/domain/models/work_item_query.py`
- `app/schemas/work_items.py`
- `tests/integration/test_work_items.py`
- `tests/unit/application/test_work_items.py`
- `tests/unit/infrastructure/storage/test_work_item_queries.py`
- `tests/postgres/test_work_item_queries.py`
- `docs/codex/reports/phase_22c_report.md`

Modified/extended (the last two were already untracked Phase 22B files):

- `app/api/dependencies.py`
- `app/api/router.py`
- `app/main.py`
- `app/domain/interfaces/business_work_item_repository.py`
- `app/infrastructure/storage/repositories/business_work_item.py`

Ignored `.phase22c-*.log` files (including JUnit XML in `.junit.log` artifacts) hold local diagnostics, the preservation manifest and the guarded local test runner. No credential is written to those artifacts. No frontend or dependency change.

## 3. Routes and strict schemas

Namespace: `/api/v1/work-items`.

| Method/path | Behavior |
|---|---|
| POST root | Source-free manual create, 201; normalized owned replay, 200; owned Location path on both |
| GET root | Bounded owned filters, computed overdue, no total count or source collection |
| GET /{item_id} | Owned current detail; empty sources in this manual-only slice |
| PATCH /{item_id} | Title, description, complete due object, direct context; expected_version required |
| POST /{item_id}/status | Explicit transition/reopen with expected_version |
| POST /{item_id}/archive | Versioned independent archive |
| POST /{item_id}/restore | Versioned restoration |
| GET /{item_id}/events | Bounded stored journal ordered by version, ordinal and ID |

Request/response models forbid extra fields. Creation accepts creation_key, action/obligation kind, normalized title/description, optional typed due and context, and only an empty source collection. Owner/actor/status-at-create/version/timestamps/origin/execution fields are rejected. PATCH distinguishes omitted values from null: null clears description/context, but title/due cannot be null; `due.kind=none` clears the due value. Version and reopen body fields use strict integer/boolean validation. Query models reject unknown fields, invalid bounds and conflicting filters. Response schemas omit internal ownership, actor IDs, creation keys and digests. Events expose only typed minimal metadata.

OpenAPI documents the new endpoints and replay response. Existing workflow-actions routing/behavior remains intact. No candidates, from-analysis, event-write or hard-delete endpoint exists.

## 4. Authentication, ownership and errors

Every route uses `require_authenticated_communications_analyze`. Missing/invalid authentication and disabled-auth mode return 401; absent analyze capability returns 403. Manual source-free creation requires no read capability or mailbox. Existing IdentityResolver binds verified issuer/subject to internal users.id; creation resolves/creates the mapping, reads do not create it. Unmapped global list returns an empty page; object/context-filter operations return 404.

Every lookup/list/mutation/event query is owner scoped. A Platform Owner has no foreign-object bypass. Context filters validate ownership even when no matching items exist. Unknown and foreign references return the same 404 body. Centralized handlers reuse ErrorResponse shape with approved 409 conflict codes; repository/UoW failures map to sanitized 503. Validation returns 422. No SQL/driver message is exposed.

The service depends only on identity and persistence. No AI, mailbox, attachment, scanner, parser or workflow executor is added to its dependency graph. HTTP dependency sentinels fail tests if provider/scanner/connector/executor construction occurs. The service adds no payload logging; log-sentinel tests verify business text and injected persistence secrets remain absent.

## 5. Manual creation and idempotency

CreationIntent and Phase 22B create_owned remain authoritative. Server binds ownership, status=open, version=1, creation_origin=manual, genuine UTC times, no confirmation actor/time/candidate key and zero sources. Root and initial created event persist atomically. One UoW commit follows successful writes. Optional target context is checked/locked within that transaction.

Same owner/key/normalized intent returns the current stored item with 200 and the same Location, without a duplicate event. Changed intent returns 409 `work_item_creation_key_conflict`. Retry after a lost response or subsequent mutation returns the current item. Creation needs neither mailbox nor context. Application entry also rejects nonempty sources and nonmanual origin independently of HTTP validation.

## 6. Lifecycle and concurrency

The API uses existing typed WorkItemCommand and repository mutation logic. Every mutation checks ownership and positive expected_version before no-op handling. Stale requests return `work_item_version_conflict`; active transitions, explicit terminal reopening, terminal edit prohibition and archived read-only behavior follow ADR-030. Archive is separate from status; repeated archive/restore can be valid no-ops.

No-op requests leave version, updated_at and journal unchanged. Actual mutations increment exactly once and append genuine ordered events within the same transaction. Commit-failure API tests verify rollback of item changes and journal rows, including creation. Existing PostgreSQL version/creation race and savepoint recovery tests were rerun. Tracking never invokes execution or Send.

## 7. Typed due values, filters and pagination

Reuses the Phase 22B discriminated none/date/datetime values, IANA zone validation, offset round-trips and DST gap/fold checks. Date-only values preserve ISO calendar dates; timed values retain confirmed zone and persist UTC. No date-only UTC-midnight conversion occurs. Datetime filter bounds normalize to UTC before binding, including SQLite, so differently expressed equal instants compare equally.

Filters: kind, one status, archive=active/archived/all (default active), owned current context or unassociated=true, due_kind, inclusive date-only range, inclusive aware datetime range, overdue=true/false. Ranges infer mode when omitted; mixed/reversed/conflicting ranges are rejected. `sort=due_asc` requires explicit date/datetime mode. Default sort is created_at DESC,id DESC; due sort is typed due ASC,id ASC. Default limit 20, max 100, nonnegative offset. No count/search queries.

One aware UTC reference instant is passed from the list endpoint to persistence and every response projection. PostgreSQL compares due_date against `CAST(timezone(due_timezone, reference_instant) AS DATE)` in the same SQL statement as owner/filter/order/limit/offset. Timed overdue compares instants strictly. Only active unarchived items are overdue; false includes terminal/archived items when other filters allow them. SQLite lacks IANA SQL support, so its read transaction loads distinct eligible zone names only, builds calendar cutoff predicates and still filters/paginates items in SQL. Neither path fetches all items for application/browser filtering.

Portable query tests compare SQL results against the domain predicate at London/New York DST boundaries, Lord Howe's half-hour transition and Apia's skipped calendar day, plus extreme-offset zones and timed equality. They exercise multiple pages, terminal/archive exclusion, inclusive bounds, inferred modes, offset equivalence and ID tie-breakers. Query instrumentation checks SQL LIMIT/OFFSET/owner predicates and absence of count queries.

## 8. Context integration and history

New association validates owned active context under the Phase 22B FOR UPDATE locking contract, held to commit and serialized with context archival. Existing links to archived contexts remain usable for allowed progress/detachment; context archive does not change item status/archive. Combined detail edit and move records edited under the old context, disassociation under the old, then association under the new, with one version/timestamp and increasing ordinals. Explicit detachment is supported; terminal items must reopen first.

History uses stored events, not inferred updates. It retains no historical title/description snapshots or internal owner/actor details. No existing context communication-link behavior or timeline projection changes; timeline integration remains a later authorized slice.

## 9. Test matrix and executed results

| Suite / evidence | Passed | Failed/errors | Skipped |
|---|---:|---:|---:|
| New HTTP API tests | 56 | 0 | 0 |
| New application tests | 10 | 0 | 0 |
| New SQLite query tests | 9 | 0 | 0 |
| New PostgreSQL query tests | 9 | 0 | 0 |
| Existing Phase 22B domain tests | 85 | 0 | 0 |
| Existing Phase 22B SQLite repository tests | 86 | 0 | 0 |
| Complete PostgreSQL suite (includes new 9 and existing tracking 93) | 196 | 0 | 0 |
| **Final focused run (34.14 seconds)** | **442** | **0** | **0** |
| **Complete backend regression (156.53 seconds)** | **3,034** | **0** | **0** |

Rows overlap; they are not additive. Phase 22C adds 84 tests to the 2,950-test baseline. The final focused run includes all API/application/SQLite query tests, the entire PostgreSQL suite and existing tracking domain/SQLite repository tests. JUnit evidence: `.phase22c-focused.junit.log`, `.phase22c-full.junit.log`. Full regression ran after the final API OpenAPI replay documentation and handler formatting changes.

Coverage includes all eight routes' authentication/capability/disabled-auth gates, owner isolation and Platform Owner non-bypass, mailbox-free create, strict authority/source/due input rejection, normalized replay/changed-intent conflict, lost-response retry, current-state replay, lifecycle/version/no-op/archive rules, context moves/detachment/archival, atomic rollback, event ordering/privacy/pagination, typed dates/ranges/overdue and safe failures. PostgreSQL also executes the retained real parallel creation/version/context-lock cases. Existing workflow/context and full backend regression tests remain green.

Final independent checks:

- `python -m ruff check .`: PASS.
- `python -m pip check`: PASS, no broken requirements. Only a non-writable pip-cache warning.
- `git diff --check`: PASS; all new source/report files additionally checked for trailing whitespace.
- `python -m alembic heads`: `22b0001 (head)`.
- Baseline SHA-256 preservation: 29 pre-existing files unchanged; two tracking repository files intentionally extended.
- Frontend checks: not applicable; frontend unchanged.

## 10. PostgreSQL evidence and safety

Verified actual running container `eci-phase22b-postgres`, image `postgres:16`, mapping `127.0.0.1:5435 → 5432`, configured database `eci_test`, SQL current_database(), server_version_num 16 and alembic revision 22b0001 before invoking tests. The session initially had no ECI_POSTGRES_TEST_DATABASE_URL. The local runner reads only the disposable container's configuration internally, builds the URL without printing/storing credentials, applies the existing safety guard and passes it to pytest's child environment. No unknown/cloud database was used. Tests reuse existing PostgreSQL fixtures and their migration/truncation safety checks.

The complete PostgreSQL suite includes the original 93 tracking cases (creation/version races, both context archive/association lock orderings, rollback/atomicity and migration rehearsal) and 9 new SQL filter cases. This phase's PostgreSQL evidence is agent-observed, not inferred from earlier operator reports. No skipped test is counted as a pass.

## 11. Reproduction and environment notes

Local diagnostic runner: `python .phase22c-local-tests.log focused` and `python .phase22c-local-tests.log full`. It verifies the exact container/host/port/database/version/revision on every invocation and does not echo secrets. Equivalent standard commands after securely setting the dedicated URL and verifying the target are:

```sh
python -c 'import os; from tests.postgres.safety import require_safe_postgres_test_database_url; from sqlalchemy.engine import make_url; u=make_url(require_safe_postgres_test_database_url(os.environ["ECI_POSTGRES_TEST_DATABASE_URL"])); assert (u.host,u.port,u.database)==("127.0.0.1",5435,"eci_test")'
python -m pytest tests/integration/test_work_items.py tests/unit/application/test_work_items.py tests/unit/infrastructure/storage/test_work_item_queries.py tests/postgres tests/unit/domain/test_business_work_item.py tests/unit/infrastructure/storage/test_business_work_item_repository.py -q
python -m pytest -q
python -m ruff check .
python -m pip check
git diff --check
```

The initial sandbox HTTP run stalled before producing test results and was interrupted; it is not a pass or failure. Approved outside-sandbox local runs completed. One intermediate SQLite assertion counted transaction BEGIN as a SELECT; it was fixed to count SELECT statements and the final query tests pass. An early PostgreSQL suite passed 195 before the extra offset-equivalence case; final counts below supersede it. No guards were weakened.

## 12. Migration and cloud boundary

No migration added or edited. Repository head remains **22b0001**. Existing migration tests exercised only disposable local databases. No schema defect or additive migration approval was needed. Cloud resources touched: **none**. No Azure/AWS access, IAM/secrets/infrastructure change, deployment, paid provider call, live mailbox/attachment retrieval or email send occurred.

## 13. Limitations, deviations and verdict

**PASS — Phase 22C manual tracking API and local validation complete.** All required local gates passed, including independently observed PostgreSQL concurrency/filter/transaction tests and full regression. No outstanding implementation blocker.

Manual detail currently has an empty source collection, consistent with the source-free scope; source availability and candidate/confirmation behavior belong to 22D. No frontend, context timeline extension, reminders, recurrence, assignment or calendar integration. Offset pagination is deterministic for unchanged data, not snapshot-stable across concurrent requests. PostgreSQL and application timezone databases must remain compatible; the executed parity cases cover the specified unusual transitions, not every historical IANA transition. No load benchmark or cloud certification is implied. No unresolved ADR-030 deviation or known failing test.

## 14. Next action and stop boundary

Review the Phase 22C changes and this evidence. Begin Phase 22D only after explicit operator authorization. Nothing was staged, committed or pushed; Phase 22D has not started.

## 15. Final repository state

Branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index unchanged, nothing staged.

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
?? app/application/services/work_items.py
?? app/domain/interfaces/business_work_item_repository.py
?? app/domain/models/business_work_item.py
?? app/domain/models/business_work_item_event.py
?? app/domain/models/business_work_item_source.py
?? app/domain/models/work_item_due.py
?? app/domain/models/work_item_intent.py
?? app/domain/models/work_item_query.py
?? app/infrastructure/storage/repositories/business_work_item.py
?? app/schemas/work_items.py
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/codex/reports/phase_22b_report.md
?? docs/codex/reports/phase_22c_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
?? tests/integration/test_work_items.py
?? tests/postgres/test_business_work_item_repository.py
?? tests/postgres/test_work_item_queries.py
?? tests/unit/application/test_work_items.py
?? tests/unit/domain/test_business_work_item.py
?? tests/unit/infrastructure/storage/test_business_work_item_repository.py
?? tests/unit/infrastructure/storage/test_phase22b_migration.py
?? tests/unit/infrastructure/storage/test_work_item_queries.py
```
