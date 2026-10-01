# Phase 22B — Domain, Persistence & Atomic Event-History Foundation

**Verdict: PASS — the PostgreSQL blocker has subsequently been resolved, based on operator-reported local terminal results.** The operator reports all 93 Phase 22B PostgreSQL tests, all 187 PostgreSQL tests and the complete 2,950-test backend regression passing. These subsequent results were not observed or rerun by Codex. The earlier blocked validation record is preserved below. No Phase 22C work is authorized or started.

## 1. Verified baseline and preservation

Initial and resumed branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77` (Phase 21 closure). Parsed revision declarations before editing: 11 revisions, sole head `21d0001`, parent `20c0001`; `22b0001` was unused. No conflicting implementation or unexpected baseline change was found. Rechecked the branch, HEAD, complete working tree and partial implementation after the operator's resume instruction.

Read the repository `AGENTS.md` and the complete readiness assessment, ADR-030, Phase 22 roadmap and Phase 22A report. The repository instruction search found no nested `AGENTS.md`. Inspected existing domain types, owner-scoped repositories, SQLAlchemy models, UoW, migrations, PostgreSQL safety/fixture code and BusinessContext archive transactions. B1–B6 were not reopened.

Initial working-tree inventory:

```text
 M docs/decisions/README.md
 M docs/roadmap/README.md
?? AGENTS.md
?? docs/codex/reports/phase_22_readiness_assessment.md
?? docs/codex/reports/phase_22a_report.md
?? docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md
?? docs/roadmap/phase-22-action-deadline-obligation-tracking.md
```

All seven files above are preserved byte-for-byte, including the two already-modified indexes. Preservation SHA-256 values:

| File | SHA-256 |
|---|---|
| `AGENTS.md` | `1160a91739c6030b5cd3c2cc03c4d1b44ff1ac7039b473523963ef27c14813d7` |
| `docs/decisions/README.md` | `d0fb59c03ae21b76868133804cb81224f89ea09edd42cec24af108699944c3fb` |
| `docs/roadmap/README.md` | `6fcb2de9ec872a3675194d8d1fd865aef22a8fc9fcf2a641cc241005cb2234bc` |
| `phase_22_readiness_assessment.md` | `12f6a5ce220f6e9c8e4bf364bac12958d8c0bc5b079dda2f16e2f2d7a3770cf2` |
| `phase_22a_report.md` | `577c75b6beebbddc3a4a3c99fb6eff7f51bd8d74667dd4948a5dbdad0d44d347` |
| `ADR-030-action-deadline-and-obligation-tracking.md` | `d780d79bf3a834a880b97c59fed522937461aa0caaf8fded95b1735ff8ef0add` |
| `phase-22-action-deadline-obligation-tracking.md` | `bd244d19582df080f483bd4b0a88b2639fc26d55a31889d6a852021e52b098cc` |

No existing migration was changed, no prior uncommitted work was discarded, and nothing was staged, committed, pushed, reset or stashed.

## 2. Exact Phase 22B file inventory

Created:

- `alembic/versions/22b0001_business_work_items.py`
- `app/domain/interfaces/business_work_item_repository.py`
- `app/domain/models/business_work_item.py`
- `app/domain/models/business_work_item_event.py`
- `app/domain/models/business_work_item_source.py`
- `app/domain/models/work_item_due.py`
- `app/domain/models/work_item_intent.py`
- `app/infrastructure/storage/repositories/business_work_item.py`
- `tests/postgres/test_business_work_item_repository.py`
- `tests/unit/domain/test_business_work_item.py`
- `tests/unit/infrastructure/storage/test_business_work_item_repository.py`
- `tests/unit/infrastructure/storage/test_phase22b_migration.py`
- `docs/codex/reports/phase_22b_report.md`

Modified:

- `app/domain/enums.py` — tracking kind, status, origin, source and event enums.
- `app/domain/exceptions.py` — owned-reference miss and typed tracking conflicts.
- `app/domain/interfaces/persistence_unit_of_work.py` — abstract tracking repository property.
- `app/infrastructure/storage/models.py` — the three additive mapped tables and constraints.
- `app/infrastructure/storage/unit_of_work.py` — repository binding and lifecycle cleanup.
- `tests/postgres/alembic_checks.py` — all three tables in the schema inventory.
- `tests/postgres/conftest.py` — explicit tracking-table cleanup in the existing guarded fixture.
- `tests/support/in_memory_persistence.py` — explicit unsupported tracking port on the legacy fake; tracking tests use real SQL transactions.
- `tests/unit/infrastructure/storage/test_alembic.py` — revision head and table inventories.
- `tests/unit/infrastructure/storage/test_models.py` — additive table inventories.
- `tests/unit/infrastructure/storage/test_phase21d_migration.py` — current-head assertion only; Phase 21 migration behavior remains tested unchanged.

Generated local test logs are diagnostic artifacts, not application changes. No frontend, HTTP route, AI/provider, workflow-execution, context service or account-erasure endpoint changed.

## 3. Domain and repository foundation

`BusinessWorkItem` is an immutable domain value. The creation factory binds internal owner, UUID, open status, version 1, origin/confirmation keys and genuine server timestamps. Typed commands produce a new validated value and its ordered event sequence together. The repository accepts creation intent or commands, never an arbitrary replacement aggregate or caller-supplied journal.

The ADR transition matrix is implemented, including explicit terminal reopen, terminal business-edit rejection, independent archive/restore, and owner/version checks for no-ops. No-op operations create no event and increment no version. Each actual mutation increments once, including combined detail/context changes. Completion is a user declaration only.

Due values discriminate `none`, `date` and `datetime`, reject extra fields, validate ISO dates and explicit IANA zones, reject naive times, DST gaps and offset/zone mismatches, and preserve explicit disambiguation of repeated times. Machine-local/posix/right aliases are rejected. Date-only values remain calendar dates; timed storage is UTC with the confirmed zone retained. Overdue is computed only for active, unarchived items. Tests include New York repeated times, London DST, Lord Howe's half-hour transition and Apia's skipped calendar date.

The port provides owned create/replay, get, mutation, immutable source reads, bounded ordered item history and owner/context-filtered history. It exposes no independent source-write or event-write/update/delete operation. Item histories sort by version, ordinal and ID; context history sorts by occurrence descending and ID ascending.

## 4. Migration and complete table inventory

Revision **`22b0001`**, down revision **`21d0001`**. It creates all three tables at once, with no backfill or Phase 20/21 data/JSON change. No 22D migration is introduced.

| Table | Complete column inventory |
|---|---|
| `business_work_items` (23) | `id`, `user_id`, `kind`, `status`, `title`, `description`, `business_context_id`, `due_kind`, `due_date`, `due_at`, `due_timezone`, `completed_at`, `cancelled_at`, `archived_at`, `created_at`, `updated_at`, `version`, `creation_origin`, `confirmed_by_user_id`, `confirmed_at`, `creation_key`, `creation_request_hash`, `origin_candidate_key` |
| `business_work_item_sources` (14) | `id`, `work_item_id`, `user_id`, `source_kind`, `analysis_id`, `attachment_analysis_id`, `connector_account_id`, `provider_message_id`, `provider_attachment_id`, `candidate_field`, `candidate_index`, `candidate_digest`, `source_key`, `linked_at` |
| `business_work_item_events` (10) | `id`, `work_item_id`, `user_id`, `actor_user_id`, `event_type`, `occurred_at`, `item_version`, `event_ordinal`, `context_at_event_id`, `metadata` |

All primary keys are UUIDs. Root ownership references `users.id ON DELETE CASCADE`; unique `(id,user_id)` supports both composite child ownership FKs with `ON DELETE CASCADE`. The current context has a single nullable FK with `ON DELETE SET NULL`, leaving the owner untouched. Source analysis/connector IDs and historical context IDs are opaque retained references without source-deletion cascades. Event JSON uses JSON on SQLite and JSONB on PostgreSQL.

Checks cover enums, bounded normalized title/description, whitespace-only provider identifiers, discriminated due nullability, terminal timestamp pairing, timestamps relative to creation, positive versions, origin/confirmation consistency, actor equality, locator all-or-none consistency, typed source combinations and lowercase SHA-256 digests. Explicit null branches prevent SQL UNKNOWN from accepting incomplete combinations. ASCII creation keys use dialect-specific equivalent checks plus the shared 1–128 length check. IANA database validation and bounded typed event JSON remain domain responsibilities, as specified by ADR-030.

Unique constraints: `(user_id,creation_key)`, nullable `(user_id,origin_candidate_key)`, `(work_item_id,source_key)`, and `(work_item_id,item_version,event_ordinal)`.

Explicit lookup indexes:

- `ix_bwi_owner_created`: `(user_id,created_at,id)`
- `ix_bwi_owner_status_at`: `(user_id,status,due_at,id)`
- `ix_bwi_owner_status_date`: `(user_id,status,due_date,id)`
- `ix_bwi_owner_context`: `(user_id,business_context_id,created_at,id)`
- `ix_bwie_owner_item`: `(user_id,work_item_id,occurred_at,id)`
- `ix_bwie_owner_context`: `(user_id,context_at_event_id,occurred_at,id)`

Downgrade inspects **all three** tables before destructive DDL and refuses if any contains data. PostgreSQL first acquires table locks to prevent inserts between inspection and removal. Only an entirely empty tracking schema is dropped, children before root. No populated tracking data is deleted to make downgrade succeed.

## 5. Atomicity, provenance and idempotency

Repositories share the caller's UoW session and never commit. Creation inserts root, immutable initial sources and the created event in one savepoint within the outer transaction. Mutation locks the owned item, checks the expected version, conditionally updates `id + user_id + expected_version`, and appends the domain-generated events in the same savepoint. The item lock also makes validated no-ops serialize with mutations on PostgreSQL.

Creation intent uses version-1 canonical compact UTF-8 JSON, stable object-key ordering, expanded defaults, trimmed business text, canonical UUIDs, sorted source sets, exact provider identifiers, UTC timed values with six fractional digits and unchanged calendar dates/confirmed zones. Candidate helpers validate stored candidate shapes before hashing, preserve stored optional-value presence and advisory date spelling, and hash typed versioned locators for exact origin identity. Arbitrary unvalidated payloads are not accepted by the typed identity helpers.

Owned key lookup precedes context/source availability checks. Same key plus same normalized intent returns the current owned item without new writes, including after source deletion or item archive. Changed intent conflicts. A new key for an existing exact origin candidate conflicts with an owned item reference. Only the designated origin is item-unique; other evidence does not trigger merging. Sources are bounded to ten distinct references and an AI-confirmed intent must include its designated origin source.

Database uniqueness remains authoritative for concurrent creation. On integrity failure, the nested transaction is rolled back **before** owner-scoped conflict recovery. Unrecognized integrity failures become sanitized persistence errors. No query is attempted inside an aborted savepoint. Source and event failure injection, outer rollback and commit failure tests verify no partial durable writes on SQLite. PostgreSQL counterparts were authored but unexecuted during the earlier Codex-observed validation; subsequent operator-reported PostgreSQL passes are recorded in section 7.

The internal repository checks existing source/connector ownership and persisted provenance tuples without provider I/O. Candidate projection, reloading/digest confirmation orchestration, final HTTP permissions and replay responses remain the expressly deferred 22C/22D work. The internal `CreationIntent` is not a public request schema or proof that those services are delivered.

## 6. Ownership, context locking and history

Every root/source/event/context lookup is owner-scoped. The test foreign user carries the Platform Owner role; it receives no bypass. Event actors are bound to the owned item, not accepted separately from a client. Account erasure works through both SQL deletion and the existing ORM user-deletion path in the SQLite contract tests.

Inspected `SqlAlchemyBusinessContextRepository.save_owned`: it performs an owned SQL UPDATE, including archive status, in the caller's transaction. New associations acquire `SELECT ... FOR UPDATE` on the same owned context row and recheck active state with `populate_existing=True`. PostgreSQL's UPDATE row lock conflicts with this lock; a weaker KEY SHARE lock would not suffice. Locks remain through the outer commit. **No adjustment to Phase 20 implementation was necessary.** Runtime serialization validation was initially blocked; the subsequent operator-reported PostgreSQL results resolve that gate (section 7).

Context archive leaves existing item status/archive untouched. Existing items can progress/edit/detach subject to their own lifecycle. New associations to an archived context fail. A move emits removal under the old context and addition under the new context, at one actual timestamp and resulting version with increasing ordinals. Detail edits occur first under the old context. History remains with its original context; no creation/association is backdated or inferred.

Event payloads are event-specific frozen types with a canonical 8 KiB cap. They contain changed field names, relevant typed due/status/context transitions and creation origin. They retain no old title/description text, raw source content, prompts or provider payloads.

## 7. Validation results and environment boundaries

### Earlier Codex-observed validation (historical)

The following record preserves the earlier blocked environment and test results; it is superseded for the current PostgreSQL gate and verdict by the subsequent operator-reported results below.

During this earlier validation, all database use was confined to explicit in-memory SQLite or pytest-created disposable SQLite files. Existing PostgreSQL guards were preserved: `ECI_POSTGRES_TEST_DATABASE_URL`, `postgresql+psycopg`, loopback host and an `eci_test` database name are required before connection/migration/truncation.

The dedicated PostgreSQL URL was unset. Local Docker inspection was attempted with approved sandbox escalation; the Docker socket/daemon was unavailable. No `postgres`, `initdb`, `pg_ctl` or conventional installed PostgreSQL server binaries were found. No unknown database was contacted, PostgreSQL database connected, or cloud resource created.

### Final focused checks

Command: `python -m pytest` with the seven files below, `-q` and local JUnit output.

| Suite | Passed | Failed/errors | Skipped |
|---|---:|---:|---:|
| `tests/unit/domain/test_business_work_item.py` | 85 | 0 | 0 |
| `tests/unit/infrastructure/storage/test_business_work_item_repository.py` | 86 | 0 | 0 |
| `tests/unit/infrastructure/storage/test_phase22b_migration.py` | 5 | 0 | 0 |
| Existing Alembic inventory/configuration tests | 19 | 0 | 0 |
| Existing model tests | 16 | 0 | 0 |
| Existing UoW tests | 7 | 0 | 0 |
| `tests/postgres/test_business_work_item_repository.py` | 0 | 0 | 93 |
| **Total** | **218** | **0** | **93** |

SQLite evidence covers the full lifecycle/reopen matrix, archive/restore, dates/DST, source bounds/types, immutable intent, source/candidate identity, owned replay/conflicts, child owner and actor checks, every due/confirmation null combination, event order/privacy, failure rollback, context archive/move semantics, retained sources, account erasure and UoW failure cleanup.

The PostgreSQL file reuses the same 86 portable repository cases and adds seven PostgreSQL cases: three parallel creation modes (same key, changed intent, exact candidate), one expected-version race, two context-lock orderings and one real migration rehearsal. **All 93 were blocked/skipped in this earlier run, not PostgreSQL passes.** Compiling PostgreSQL DDL is only a static compatibility check, not runtime PostgreSQL evidence.

### Migration evidence

Five executed migration tests cover additive upgrade preserving a persisted XLSX analysis and its `tabular_result`, complete column/check/index inventories, successful empty downgrade/re-upgrade, populated downgrade refusal with the item and revision intact, all-three-table pre-DDL inspection even if only a child is reported populated, and SQLite/PostgreSQL DDL compilation. Prior Phase 21 migration tests remain part of regression; no applied migration was rewritten.

### Full backend regression

**Final command:** `python -m pytest -q --junitxml=.phase22b-full-final.xml` (approved outside-sandbox execution, offline/local scope).

**Result: 2,763 passed, 0 failed, 0 errors, 187 skipped; 2,950 collected; 120.06 seconds.** All 187 skips were guarded PostgreSQL tests: 94 existing and 93 new. Thus this earlier PostgreSQL gate had 0 executed tests and 187 blocked/skipped cases overall; skipped cases are not counted as passes. The final focused run took 3.85 seconds.

The sandbox attempts stalled in Starlette TestClient startup before the first test completed. Diagnostic stack output located the stall; those runs were interrupted and are not counted as passes or failures. The operator-approved outside-sandbox offline run completed normally. Its first run reported **2,705 passed, 2 failed, 142 skipped**; both failures were outdated exact schema inventories. Those inventories were updated. An intermediate complete run then reported **2,760 passed, 0 failed, 184 skipped**. The final run includes the additional SQL whitespace constraint coverage.

The initial focused domain run had **72 passed, 2 failed** due to Python fold-sensitive equality between zone-based and fixed-offset datetimes. The value representation was corrected to retain the chosen fixed offset, and both cases now pass. These resolved intermediate failures are not hidden or counted as current failures.

### Other checks

- `python -m ruff check .`: PASS.
- `python -m pip check`: PASS, no broken requirements. Pip emitted only a non-writable-cache warning.
- `git diff --check`: PASS; new files additionally inspected for trailing whitespace/conflict markers.
- Frontend checks: not run; no frontend change.
- Earlier PostgreSQL runtime gate: BLOCKED by unavailable local infrastructure; no safety guard relaxed. Subsequently resolved by the operator-reported results below.

### Subsequent operator-reported local validation — blocker resolved

Evidence source: **operator-reported terminal results**, supplied for this documentation update. Codex did not observe these executions, rerun tests or independently inspect the container/database for this update.

- Disposable PostgreSQL 16 container: `eci-phase22b-postgres`.
- Database: `eci_test`, accessible through `127.0.0.1:5435`.

| Suite | Operator-reported result | Duration |
|---|---|---:|
| Phase 22B PostgreSQL suite | 93 passed | 4.98 seconds |
| Complete PostgreSQL suite | 187 passed | 9.89 seconds |
| Complete backend regression | 2,950 passed, 0 failed, 0 skipped | 128.62 seconds |

These subsequent results resolve the earlier local PostgreSQL blocker and support the updated Phase 22B **PASS** verdict. The historical skips and intermediate failures above remain part of the record; they are not relabeled as passes. The suite totals overlap and are not additive.

## 8. Limitations, verdict and next action

**PASS** describes the implemented foundation, the earlier Codex-observed local checks and the subsequent **operator-reported terminal results** for PostgreSQL and complete backend regression. The previously blocked PostgreSQL concurrency/locking/transaction/migration gate is resolved on that reported evidence. Codex did not independently observe or rerun the subsequent executions.

No public tracking APIs, candidate-projection/confirmation service, frontend, due-filter query API, provider contract/prompt or automatic business action was introduced. The legacy in-memory test UoW intentionally cannot simulate tracking; future tracking application tests should use the transaction-capable fixtures or explicitly add a suitable fake in their authorized slice. PostgreSQL runtime acceptance relies on the operator-reported results rather than Codex-observed execution.

Cloud resources touched: **none**. No Azure/AWS access, production migration, live mailbox/attachment retrieval, paid provider invocation, execution/send, commit or push occurred. Local results imply no cloud, provider or live-mailbox certification.

Recommended next action: review this foundation and obtain explicit operator authorization before any **Phase 22C** work. Phase 22C is not authorized or started by this documentation update.

This follow-up changes only `docs/codex/reports/phase_22b_report.md`. No implementation or migration changes, test reruns, commits, pushes or cloud access were performed; `AGENTS.md` and all other existing uncommitted Phase 22 changes were preserved.

## 9. Final repository state

Branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index unchanged; nothing staged. The two documentation-index modifications and five original untracked files below predate 22B and remain preserved.

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

Local JUnit output is retained as ignored `.phase22b-*.junit.log` diagnostic files alongside the ignored test logs; these are excluded from the source-change inventory.
