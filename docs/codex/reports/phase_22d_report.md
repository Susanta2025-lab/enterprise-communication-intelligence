# Phase 22D — Verified Provenance & Human-Confirmed Analysis Conversion

Date: 2026-09-26. Scope: Phase 22D implementation and safe LOCAL validation only.

## 1. Baseline, resumption and preservation

Branch `master`; HEAD `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. The index was empty. Repository Alembic head was **22b0001** at initial inspection and resumption. Read AGENTS.md, ADR-030, the Phase 22 roadmap and Phase 22A–22C reports. Inspected the actual aggregate, source/event models, CreationIntent/canonicalization, repository/savepoints, UoW, routes, schemas, authentication/capabilities, identity resolution, persisted analysis/tabular contracts and connector ownership conventions.

The initial inspection identified the observation-length mismatch described below and stopped without edits. The operator explicitly authorized its narrow correction and continuation. At the subsequent resume instruction, the implementation and initial test evidence already existed; work continued from those files. The latest intermediate focused result then was 314 passed and one obsolete Phase 22C route-exclusion assertion. No implementation was restarted or discarded.

Original operator-reported baseline results were 3,034 complete backend passes and 196 PostgreSQL passes. They were not substituted for this phase's independent executions. The original working-tree inventory was:

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

A SHA-256 manifest captured all 43 pre-existing modified/untracked files before Phase 22D edits. The ten files listed as extended below contain intentional Phase 22D changes; the other **33 files remain byte-for-byte unchanged**, including untracked AGENTS.md, previous reports, ADR/roadmap files, migration 22b0001 and the existing Phase 22B tests. Nothing was staged, committed, pushed, reset, cleaned, stashed or removed. Ignored `.phase22d-*.log` artifacts hold local diagnostics, JUnit XML, the baseline manifest and the guarded runner; they contain no stored database credentials.

## 2. Exact Phase 22D implementation inventory

Added:

- `app/application/services/work_item_provenance.py`
- `app/domain/models/work_item_provenance.py`
- `docs/codex/reports/phase_22d_report.md`
- `tests/integration/test_work_item_conversion.py`
- `tests/postgres/test_work_item_conversion.py`
- `tests/unit/infrastructure/storage/test_work_item_conversion.py`

Modified/extended, including files already untracked from Phase 22B/C:

- `app/api/routes/work_items.py`
- `app/application/services/work_items.py`
- `app/domain/exceptions.py`
- `app/domain/interfaces/business_work_item_repository.py`
- `app/domain/models/business_work_item_source.py`
- `app/domain/models/work_item_intent.py`
- `app/infrastructure/storage/repositories/business_work_item.py`
- `app/main.py`
- `app/schemas/work_items.py`
- `tests/integration/test_work_items.py`

No frontend, dependency, provider-contract, prompt, workflow-execution, infrastructure or migration file changed in this phase. The existing Phase 22C test that prohibited future candidate/conversion routes now asserts their presence, retains workflow-route separation and checks absence of public source-write/hard-delete routes.

## 3. Discovered mismatch and authorized correction

`TabularAnalysisResult.potential_action_mentions` permits strings up to **300 characters**; `potential_dates` permits **200**. The existing `candidate_digest` rejected every string over 200, incorrectly excluding valid 201–300-character action observations. Ordinary communication/attachment `ActionItem` values are typed dictionaries; their description contract is distinct from the reviewed work-item title contract.

The digest helper now accepts an allowlisted candidate field and enforces its existing field-specific bound: 300 for action mentions and 200 for date observations. It validates action dictionaries through the existing ActionItem model, then hashes the **original persisted value**, not a normalized model dump. Canonical UTF-8 JSON preserves Unicode, stored optional-key presence, date spelling and complete string values; key ordering and compact separators remain unchanged. No observation is truncated, rewritten or paired with another observation.

The reviewed work-item title remains trimmed, nonblank and at most **200 characters**; description remains at most 4,000. The conversion request requires its own reviewed title, kind, complete typed due value and explicit confirmation. Tests project/hash 200-, 201- and 300-character observations, compare the full-value SHA-256, confirm with a shorter title, reject overlong titles, reject observations beyond the field contract and verify changed/tampered digest rejection. Pure digest tests also preserve optional fields and Unicode/whitespace identity.

## 4. Source and confirmation architecture

The existing Phase 22B aggregate transaction remains authoritative. `work_item_provenance` domain values define strict requested source references, an explicit versioned candidate selection, candidate responses and bounded source-detail metadata. The application provenance helper reads only existing owner-scoped analysis and connector-account repositories. `WorkItemService.create_verified` performs replay lookup, source verification, permission checks and final CreationIntent construction, then delegates atomic persistence to the existing repository/UoW.

Manual creation accepts zero to ten distinct sources. Conversion designates exactly one origin candidate; the service derives its required origin source and allows zero to nine additional explicitly requested sources. No additional evidence is inferred or merged. Source rows remain immutable after creation. Existing manual work items retain manual origin and are never rewritten into AI-confirmed items.

Public source shapes are:

- Direct communication: `{source_kind:"communication", connector_account_id, provider_message_id}`.
- Persisted analysis: `{source_kind:"communication_analysis"|"attachment_analysis", source_id, candidate?}`. An optional candidate must match that reference's kind and ID and pass server reload/index/digest verification.

Analysis-derived connector/message/attachment tuples are not client input fields. Unknown fields, user/owner/actor IDs, status/version/timestamps, workflow targets and provider credentials are rejected. Direct opaque message identifiers must be nonblank and bounded; their exact case and value are preserved.

## 5. Deterministic candidate projection

Supported persisted observations:

| Owned source | Candidate field |
|---|---|
| Communication analysis | `action_items` |
| Ordinary supported attachment analysis | `action_items` |
| XLSX/tabular analysis | `potential_action_mentions` |
| XLSX/tabular analysis | `potential_dates` |

Potential amounts are never candidates. XLSX action and date arrays remain independent: stable field order is action mentions then dates, with a separate zero-based index in each array. Matching indexes do not imply a relationship. A date observation requires a reviewed title and explicit due object; `{kind:"none"}` is an explicit choice to create no deadline. Free-text AI owner suggestions remain advisory output and never become internal ownership or assignment.

Every locator contains `projection_version`, `source_kind`, `source_id`, `field`, `index`, `digest`. Public selections must explicitly specify integer version 1; booleans, floats and unsupported versions are rejected. Malformed fields/indexes return 422. A valid-shaped locator whose stored value no longer matches returns 409 `work_item_candidate_changed`. Missing or foreign source records return the same 404.

Projection returns original observation values with advisory=true, persisted truncation flags, attachment/tabular warnings and tabular limitations. It hashes only the requested bounded page. Pagination defaults to 20, maximum 100, nonnegative offset, no total count. Empty results yield an empty page. Projection performs no tracking writes, event insertion, inference or source-content retrieval.

## 6. Routes and permission matrix

Namespace: `/api/v1/work-items`. Static routes are registered before `/{item_id}`.

| Route/operation | Capability requirements | Behavior |
|---|---|---|
| GET `/candidates` | Verified authentication + communications:analyze | Existing owned persisted history; read-only projection |
| POST root, zero/direct-text sources | Analyze | Explicit manual creation with verified optional sources |
| POST root, any mailbox-backed source | Analyze + communications:read | Every nested source independently verified |
| POST `/from-analysis`, direct-text origin/evidence | Analyze | Explicit confirmed creation |
| POST `/from-analysis`, any mailbox-backed origin/evidence | Analyze + read | Server-derived provenance determines read requirement |
| Existing-key replay | Analyze; + read if stored immutable sources are mailbox-backed | Gate before hash conflict/replay disclosure; no current-source dependency |
| GET `/{item_id}` | Analyze, owned item | Minimal retained sources plus availability |
| Existing list/mutation/event routes | Existing authenticated analyze policy | Prior ownership/lifecycle behavior retained |

AUTH_MODE=disabled remains rejected for durable tracking. No new IdP scope, Platform Owner bypass, workflow approval/execution grant or Send capability was added. Detail availability uses persisted metadata and does not assert live provider-content existence. List entries remain lightweight and do not load source collections.

## 7. Server-side ownership and provenance verification

Communication-analysis sources reload by analysis ID and internal owner, deriving any mailbox tuple from that stored row. Attachment sources reload by attachment-analysis ID and internal owner and derive the entire connector/message/attachment tuple. Actual stored attachment kind controls candidate-field applicability. Direct communication references verify an existing owned connector and supplied bounded opaque message ID; provider existence is deliberately not checked.

Every new mailbox-backed link requires its connector metadata to exist and be owned. An owned disconnected connector is acceptable historical provenance. No credential resolution or provider connection occurs. Unknown/foreign analyses, attachments, connectors and contexts have indistinguishable 404 behavior, including for a Platform Owner. Optional BusinessContext association uses the existing owned active-context validation and transaction lock.

## 8. Explicit confirmation and business review

`confirmed=true` is required as a strict boolean; omission, false and coercible strings are rejected. Title, kind, creation key, candidate and complete due value are required for conversion. Request instances are revalidated at application entry. The service reloads and verifies the selected candidate, uses only reviewed business fields and binds confirmation actor/time through the existing aggregate factory. Creation sets open status, version 1 and genuine current timestamps.

No tracking item exists merely because an analysis is produced, a candidate is retrieved, an observation is selected or a review is cancelled. There is no draft/autosave/cancel mutation endpoint. Invalid confirmation and failure tests assert zero item/source/event rows.

## 9. Idempotency, candidate uniqueness and replay

CreationIntent and shared canonical hashing remain the persistence contract. The request hash excludes analysis-derived mailbox tuples loaded later, while retaining typed requested references, candidate locator, reviewed fields, normalized due/context and confirmation. Source order is canonicalized as a set. This implements ADR-030's requested-intent rule and allows deterministic replay after deletion. Source-free manual normalization stays compatible; no existing row is rewritten or rehashed. Source-key hashing still includes the actual verified minimal provenance stored at creation.

An owner/key lookup occurs before current source or context validation. Stored source rows determine replay read permission even when original records no longer exist. Equal normalized intent returns the current item with 200 and no writes; changed intent returns 409 `work_item_creation_key_conflict`. A new key for the same exact origin conflicts with `work_item_candidate_already_tracked` and an owned Location path. New creations return 201. Same-key replay takes precedence over exact-candidate conflict. No force-duplicate or semantic merging path exists.

Database lifetime unique constraints remain authoritative. The existing nested savepoint rolls back an insertion loser before conflict recovery queries. New PostgreSQL service races cover same key, changed intent and exact candidate; both contenders are forced past the final absence check, exercising SQL uniqueness recovery. Retained repository tests also verify transaction usability after a PostgreSQL uniqueness violation. All races leave exactly one item, one source and one creation event.

## 10. Source deletion, disconnection and availability

Source references are retained without foreign keys to deletable analyses/connectors. Source deletion does not delete or alter the item or its event history. Detail resolves owner-scoped metadata and reports `availability:"available"|"unavailable"`; every source includes `provider_content_verified:false`. Disconnection alone preserves metadata availability and does not block valid historical linking/replay.

Tests confirm replay after analysis and connector deletion, disconnection, completion and archive. Mailbox-backed replay still requires read permission after deletion. Retained source references and candidate identity remain intact. A fresh creation with an absent source fails safely. No background reconciliation, provider download, reanalysis, source replacement or source-write/delete endpoint was introduced.

## 11. Atomicity, event history, security and side effects

The repository inserts the work item, initial immutable sources and actual created event in one savepoint under the UoW transaction. Confirmation actor/time and origin are part of the same root insert. Success returns only after commit. Replay inserts neither sources nor events. Created-event metadata remains the existing minimal typed payload; no historical event is fabricated from an older analysis.

Portable and real PostgreSQL tests exercise event-insertion and commit failure rollback, retention and user deletion cascade. Existing Phase 22B tests also cover SQL/ORM erasure, source/event ownership constraints, context locking and savepoint recovery. No orphan rows remain after failed creation or account erasure.

HTTP tests reuse dependency sentinels that fail if AI, mailbox connector, scanner or workflow executor construction occurs. Tracking modules have no parser, retriever, credential resolver or execution dependency. Provider prompts/contracts and workflow state machines are unchanged. Existing privacy tests and injected persistence-failure checks confirm sanitized errors and absence of business text/secret persistence details in logs. New services log no candidate values/digests, workbook content, request bodies or provider IDs. Authorized candidate responses expose only observations already within owned analysis-history access.

## 12. Executed validation results

| Suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| New Phase 22D HTTP/canonicalization tests | 69 | 0 | 0 | 0 |
| New portable conversion transaction tests (SQLite) | 3 | 0 | 0 | 0 |
| New PostgreSQL conversion/transaction/concurrency tests | 6 | 0 | 0 | 0 |
| Focused Phase 22D + retained Phase 22B/C gates | 324 | 0 | 0 | 0 |
| Complete PostgreSQL suite | 202 | 0 | 0 | 0 |
| Complete backend regression | 3,112 | 0 | 0 | 0 |

Rows overlap and are not additive. Phase 22D adds 78 tests. Focused execution took 53.25 seconds; the complete PostgreSQL suite took 11.68 seconds. The final PostgreSQL run includes the strengthened race synchronization added after the focused run. JUnit evidence is retained in `.phase22d-focused.junit.log`, `.phase22d-postgres.junit.log` and `.phase22d-full.junit.log`.

The complete backend regression passed **3,112 tests, 0 failures, 0 errors and 0 skips in 189.84 seconds**. It includes all 202 real PostgreSQL tests, retained Phase 22B/C tests, Phase 20 Context tests, Phase 21 attachment/XLSX tests, workflow approval/execution boundary tests and existing Mock/Foundry/Bedrock provider contracts with offline fixtures. No skipped test is counted as a pass.

Intermediate evidence is not hidden: an initial test fixture used an invalid extracted-content status and was corrected to the actual persisted contract; a direct-communication reference initially passed a serialized UUID into the repository lookup and was corrected to a typed UUID; the obsolete Phase 22C route-exclusion assertion was updated for this authorized phase. Intermediate runs recorded 2 passes/1 failure, 53 passes/1 failure and 314 passes/1 failure respectively. They are superseded by the results above. A sandbox TestClient run stalled before results and was interrupted; Docker inspection in the sandbox was denied. Approved local execution outside the sandbox completed without weakening guards.

## 13. PostgreSQL safety and reproduction

Before connecting, verified running container `eci-phase22b-postgres`, image `postgres:16`, exact mapping `127.0.0.1:5435 → 5432` and configured database `eci_test`. The existing `require_safe_postgres_test_database_url` guard is unchanged. The runner obtains only the disposable container's configuration internally, constructs the dedicated URL without printing/persisting it and checks SQL current_database(), PostgreSQL major version 16 and actual Alembic revision **22b0001 before test mutation**. Each test invocation repeats these checks; no inherited environment variable is assumed.

Executed commands:

```sh
python .phase22d-local-tests.log focused
python .phase22d-local-tests.log postgres
python .phase22d-local-tests.log full
python -m ruff check .
python -m pip check
git diff --check
python -m alembic heads
```

The local runner dispatches `python -m pytest -q` with the focused file inventory, `tests/postgres`, or the whole backend suite and a dedicated JUnit path. It passes ECI_POSTGRES_TEST_DATABASE_URL only to the child process. PostgreSQL evidence is actual runtime evidence, not SQLite substitution or an inferred earlier report. Existing destructive migration/truncation fixtures remain guarded and confined to disposable local databases.

## 14. Standard checks and migration/cloud boundary

- Ruff: PASS, `python -m ruff check .`.
- Dependencies: PASS, `python -m pip check`, no broken requirements; only the existing non-writable pip-cache warning.
- Whitespace: PASS, `git diff --check`; Phase 22D new files also checked explicitly.
- Repository migration head: **22b0001**. No migration added or changed.
- Frontend checks: not applicable; no frontend changes.
- Cloud resources touched: **none**. No Azure/AWS access, cloud migrations, IAM/secrets/infrastructure changes, deployments, paid model calls, live mailbox/attachment retrieval or email sends.

## 15. Limitations, deviations and readiness

**PASS — Phase 22D implementation and all required local validation gates are complete.** No known failing test or unresolved implementation blocker remains. This verdict is local and does not certify cloud deployment or live-provider behavior.

No unresolved ADR-030 architectural deviation. Candidate source-field bounds and request hashing now follow the existing persisted/ADR contracts. Observations remain advisory; meaningful business interpretation and actual due information require human review. The API cannot independently prove legal/business fulfillment or live mailbox-content existence. Availability refers to owned persisted metadata, and disconnected historical connectors can remain available. Offset pagination is deterministic for unchanged data, not a snapshot across concurrent requests. No frontend confirmation flow, timeline extension, reminders, recurrence, assignment or external-task synchronization is part of 22D.

## 16. Recommended next action and stop boundary

Review the Phase 22D changes and this local evidence. Seek explicit operator authorization before Phase 22E (the context timeline/UI slice defined by the roadmap). Phase 22E has not started. No staging, commit or push was performed; the operator's plan to commit Phase 22 together is preserved.

## 17. Final repository state

Branch: `master`. HEAD: `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`. Index empty. Complete status:

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
