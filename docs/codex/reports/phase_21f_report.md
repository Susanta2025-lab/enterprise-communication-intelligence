# Phase 21F — XLSX hardening and local release readiness

## 1. Executive summary

Phase 21F only: combined Phase 21A–E review, targeted security repairs, local
regression, PostgreSQL migrations, and documentation normalization. No product
scope expansion, new migration, infrastructure, cloud access, deployment, live
AI, commit, or push. Phase 21 remains OPEN; Phase 21G is NOT STARTED.

Final validation and verdict are recorded in sections 21–27.

## 2. Baseline

- Date: 2026-09-19; branch `master`.
- HEAD: `63669ec8bdf27158817e4fe56858fd3df3ce3086`.
- One Alembic head: `21d0001`, parent `20c0001`.
- Initial `git status --short`: 43 tracked modifications plus existing untracked
  A–E source, migration, tests, reports, roadmap, AGENTS.md, and two Phase 21D
  JUnit artifacts. No staged changes. These were preserved.
- Local dedicated container `eci-phase21d-postgres` already running at
  `127.0.0.1:55421`; initial database revision `21d0001`. Test URL passed the
  repository localhost/`eci_test` guard. Credentials were neither printed nor
  written to reports. Existing disposable test data was handled by standard
  PostgreSQL fixture truncation. No other container was changed.
- Read AGENTS.md, README, readiness assessment, A–E reports, and Phase 21 roadmap.
  Historical reports' early fail-closed gates are superseded by D/E enablement;
  no repository/task conflict or unrelated production modification was found.

Combined Phase 21 diff classification:

| Area | Reviewed changes |
|---|---|
| Security/policy | Attachment kinds, extension/MIME policy, size/container gates, scanner ordering, exceptions |
| Parser | XLSX dispatcher, openpyxl extractor, workbook models, centralized caps |
| AI | Provider interface, bounded request/result, input preparation, prompts, Mock/Foundry/Bedrock adapters and output schemas |
| Persistence/migration | `21d0001`, existing attachment row/repository/record, history, validated nullable JSONB |
| API/application | Existing Analyze orchestration and additive response; no new route |
| Frontend | Typed API fields, attachment type/icon, explicit request guard, structured panel/history |
| Tests | Policy/parser/provider, application/API/ownership, SQLite/PostgreSQL migration/storage, React regression |
| Documentation | Assessment, A–E slice reports, roadmap/index; current docs reconciled in F |

## 3. Full Phase 21 architecture reviewed

```text
metadata-only attachment listing (no bytes)
  → explicit single-attachment Analyze
  → verified (iss, sub) → internal user → owned usable connector
  → message/attachment membership and exact provenance
  → one attachment retrieval
  → byte-size and per-request budget gates
  → scanner; only CLEAN continues
  → XLSX ZIP/OOXML security validation
  → bounded openpyxl extraction
  → provider-neutral 32,768-character workbook sample
  → untrusted-data prompt fence, trusted system policy
  → AIProvider.analyze_tabular
  → bounded TabularAnalysisResult validation
  → attachment_analyses transaction
  → typed Analyze/history API response
  → escaped React text
```

Inspected listing/connected Analyze services, inspection/analysis/history,
parser dispatcher, provider call sites, repositories, routes, schemas and UI.
There is one product XLSX Analyze path. Direct parser unit entry points consume
bytes but are not separately exposed HTTP routes. The parser defensively repeats
container validation. Listing/history/context reads cannot invoke the parser or
retrieve attachment content. Identity classes remain separate; no email-keyed
authorization or cloud-specific product branch was introduced.

## 4. Security hardening results

Fourteen new synthetic container cases failed against the baseline and passed
with the repairs:

- Literal XML byte matching missed external `TargetMode` with whitespace,
  character references, or UTF-16; macro content types had the same encoding
  weakness. Security attributes now use streaming `defusedxml` parsing with
  DTD/entities forbidden. Existing dependency reused.
- Malformed XML and corrupt ZIP member reads now raise normalized unsupported
  errors instead of leaking library exceptions. CRC regression also exercises
  the real API and proves no provider call or persistence.
- XLSX inventory rejects encryption flags, duplicate members, NUL-normalized
  names, backslash/dot/drive-path ambiguity, and unsupported ZIP compression
  methods. Existing traversal, entry/size/ratio checks remain. Stricter ZIP
  checks are scoped to XLSX; DOCX policy was not broadened.
- `keep_links=False` explicitly complements `read_only=True`, `data_only=False`,
  `keep_vba=False` during openpyxl loading.

`.xlsx` alone is supported; XLS/XLSM/XLSB/CSV/TSV remain rejected. Extension,
MIME, signature and OOXML workbook identity must agree. Macros/encryption,
external relationships, external-link parts and data connections are rejected.
Embedded OLE packages remain WARN/IGNORE, never recursively opened. Formulas
(including HYPERLINK/external-reference strings) remain inert data with warnings.
No evaluation engine, workbook save/rewrite, URL resolver or parser network path.

Prompt policy and fencing keep workbook text out of system instructions. The
adapters have no workbook-triggered tools or state-mutation capability. Prompt
fencing is not a guarantee that a model can never produce misleading advice;
results remain advisory, schema-validated, and incapable of executing actions.

## 5. Resource-bound results

All established limits remain unchanged and centralized in attachment policy:

| Bound | Limit |
|---|---:|
| Outer attachment | 5 MiB |
| Per-request processed-byte budget | 10 MiB |
| ZIP entries | 512 |
| Aggregate uncompressed ZIP | 20 MiB |
| Single ZIP part | 8 MiB |
| Compression ratio | 100:1 |
| Processed sheets | 10 |
| Columns per sheet | 50 |
| Data rows per sheet | 100 (excluding inferred header) |
| Emitted cells, workbook-wide | 5,000 |
| Extracted characters | 200,000 |
| Characters per cell | 2,000 |
| Workbook AI input characters | 32,768 |

Fixed an intermediate extraction overrun: the final cell previously could take
`characters_emitted` beyond the remaining budget before serialized output was
clipped. It now clips before adding the cell; a deterministic regression checks
both structured content and count. Existing serialized-output cap still includes
formatting overhead. Trusted AI instructions/metadata add framing overhead to
the 32,768-character workbook-data cap; providers do not widen the sample.

No pandas or full-matrix materialization. Explicit iteration limits prevent
allocation from declared dimensions; openpyxl still loads workbook metadata,
styles/shared strings within the ZIP envelope. A synthetic dense 80,000-cell,
5,079,939-byte stored ZIP passed actual content policy and extracted in 0.163 s,
emitting 5,000 cells / 73,500 characters with truncation. Process peak RSS was
101.5 MiB including fixture generation. Workbook bytes remained in memory.
An earlier direct-parser probe exceeded the outer limit and was not used as
product-path evidence. This is a local single-request observation, not proof of
worst-case or concurrent 1 GiB behavior; runtime latency/memory remain live gates.

## 6. Migration validation

Only existing `21d0001` is used; no migration created or modified in F. It revises
`20c0001`, adds nullable JSONB on PostgreSQL, and extends the kind constraint.
SQLite and real PostgreSQL tests exercise:

1. XLSX rejected by the old constraint; legacy PDF/DOCX/JPEG/PNG/TXT rows valid.
2. Upgrade preserves legacy rows; new structured XLSX row can be saved/read.
3. Downgrade refuses while XLSX rows exist, before DDL, preserving data/head.
4. Remove only the synthetic XLSX row; downgrade restores exact old columns and
   constraint while preserving legacy rows.
5. Re-upgrade succeeds; unsupported spreadsheet kinds remain rejected.

Operational rule: retain `21d0001` while real XLSX history exists. Do not delete
history to force rollback. Any production retention/migration decision requires
separate authorization. See section 22 for CI-equivalent full migration cycle.

## 7. Persistence validation

Complete validated `TabularAnalysisResult` round-trips through the existing
attachment row, detail and list APIs, including all potential fields, sheet
summaries, warnings and separate limitations. The compatibility summary mapping
does not replace or discard structured output. Read validation rejects corrupt
or unbounded JSON with sanitized `PersistenceError`; arbitrary extra fields are
forbidden. Existing non-XLSX rows retain null `tabular_result`.

No new table/model of persistence, `business_context_id`, raw workbook, XML,
extracted grid, prompt, or raw provider-response column. Advisory summaries may
naturally contain selected business information; absence of raw workbook storage
does not mean AI summaries are devoid of sensitive business facts.

## 8. Failure atomicity

Application/API regressions cover authentication/ownership/provenance failure,
retrieval errors, size/budget rejection, scanner reject/error/unavailable,
container/parser failure, provider errors, malformed/invalid structured results,
and persistence failure. Downstream spies and empty stores establish ordering
and no successful analysis or workflow/business state on failure.

Added real PostgreSQL commit-failure regression: save/flush a validated XLSX
result, inject `SQLAlchemyError` at commit, and verify rollback leaves no
attachment analysis, workflow action, or BusinessContext row. Public error does
not contain the synthetic private driver detail. Normal reauthorization handling
can mark a connector unusable; this existing credential lifecycle is not an AI
business-state mutation.

## 9. Authorization/ownership validation

Authentication/scopes precede retrieval. Account ownership uses verified
`(iss, sub)` mapping to internal user ID; no email authorization key. Unknown or
foreign connectors/history are hidden per existing conventions. User and
Platform Owner both fail cross-user tests. ACTIVE/mail.read, wrong message,
wrong attachment, retrieved source-message/source-attachment mismatch and
history filters remain covered. No Phase 19 bypass or role rewrite.

## 10. BusinessContext compatibility

Existing communication provenance links derive generic
`attachment_analysis_completed` events for XLSX. Backend timeline and frontend
generic timeline tests pass without mailbox/parser/AI I/O. No context ID added
to attachment history, automatic association, or ownership mutation. Phase 20
production code remains unchanged.

## 11. Phase 22 boundary

`potential_dates`, `potential_amounts`, and `potential_action_mentions` remain
bounded strings. Compatibility `action_items=[]`, no draft reply, no Deadline,
Obligation, work item, workflow proposal, approval, payment or Send operation.
No Phase 22 implementation was added.

## 12. Provider parity

Mock, Microsoft Foundry and Amazon Bedrock use the same neutral request/result,
input cap and source-truncation semantics. Foundry and Bedrock share output
parsing/mapping and safety prompts; service validation catches malformed custom
adapter results before persistence. Provider exceptions normalize to analysis
failure with class-only logging. Offline parity: 15 cases; related input/output/
prompt cases: 23. No live Foundry, Bedrock, mailbox or cloud call.

## 13. API compatibility

Existing endpoint and request body unchanged. XLSX returns `kind=xlsx` with
validated structured `tabular_result` in Analyze/list/detail; PDF/DOCX/TXT use
null. Existing legacy image history is valid. Truncation survives parser and AI
sampling even if an adapter understates it. Warnings/limitations are separate;
provider is an opaque identifier. Backend and TypeScript tabular field sets
were compared programmatically and match. Safe existing error taxonomy reused.

## 14. Frontend hardening

Inspected E-stage types, request hook, attachment UI and structured panel;
no F frontend source change was necessary. Explicit Analyze only, same-tick
in-flight guard, sibling disabling, navigation response isolation, loading,
explicit retry and normalized error display remain covered. Null/omitted tabular
results preserve legacy history; empty sections are omitted. Both truncation
flags disclose sampling. Potential dates/amounts/actions retain advisory labels.
React interpolation escapes all values; no HTML renderer, automatic links,
formula/script execution, or client-side XLSX parser dependency. Tests include
hostile values throughout fields and accessibility checks.

## 15. Privacy/logging review

Searched inspection, parser, analysis/history, connected mailbox orchestration,
provider tabular methods, repositories, API middleware and exception handlers.
Logs contain normalized categories, IDs already used by attachment telemetry,
provider/kind, counts, size buckets, durations and truncation; no workbook bytes,
cell/formula contents, prompts, raw responses, secrets or exception bodies.
Parser has no content logging. Sentinel error tests cover provider/parser/storage
and hostile containers. New container errors suppress library exception context
at the policy boundary. No content-bearing logging was added.

## 16. Dependency/supply-chain review

Combined Phase 21 manifest delta is only `openpyxl>=3.1` (installed 3.1.5;
transitive `et-xmlfile`). This matches existing minimum-version declaration
policy; no exact-pin strategy change. Phase 21F dependency delta: none.
Existing defusedxml is reused. No pandas, SheetJS, ExcelJS, spreadsheet viewer,
or new native binary requirement. `pip check` and frontend `npm ls --depth=0`
pass. Existing node_modules were usable; no unnecessary reinstall or lockfile
change. CI retains `npm ci`. This is dependency consistency review, not a new
online CVE or live supply-chain attestation.

## 17. CI coverage assessment

`.github/workflows/ci.yml` naturally discovers all new tests. Python job installs
project/dev dependencies, runs pip check, ruff and pytest. PostgreSQL 16 job runs
upgrade/head assertion, downgrade/base/empty assertion, re-upgrade and the entire
PostgreSQL suite, including refusal-with-XLSX migration and commit-failure tests.
Frontend job uses npm ci, typecheck, lint, tests and production build.
No Phase 21 coverage gap found; no CI or deployment workflow edit. Existing CI
separates ordinary tests from PostgreSQL, avoiding global database configuration
in unrelated configuration tests. Remote CI was not triggered (no push).

## 18. Documentation changes

README now distinguishes local XLSX support from pending cloud validation.
Roadmap/index retain overall OPEN and Phase 21G not started. A–E reports preserve
historical results with explicit current-state notes. API docs specify existing
routes, nullable structured fields, bounds, advisory semantics and safe errors.
Azure/AWS runbooks add Phase 21 prerequisites and the non-destructive downgrade
policy; historical live rejection evidence remains labeled historical. Stale
AttachmentKind docstring normalized. No unrelated documentation rewrite.

## 19. Files created

Phase 21F additions only:

- `tests/unit/domain/test_phase21f_xlsx_hardening.py`
- `tests/postgres/test_phase21f_atomicity.py`
- `docs/codex/reports/phase_21f_report.md`

Local validation logs and JUnit outputs use `.phase21f-*`; initial failed-run
artifacts and all pre-existing Phase 21D artifacts were retained.

## 20. Files modified

Phase 21F edits only, including pre-existing untracked A–E files:

- `app/domain/attachment_policy.py`
- `app/domain/enums.py`
- `app/infrastructure/attachments/xlsx.py`
- `tests/unit/infrastructure/attachments/test_xlsx_parser.py`
- `tests/integration/test_phase21d_xlsx_analysis.py`
- `README.md`
- `docs/api/README.md`
- `docs/api/endpoints.md`
- `docs/api/request-response-models.md`
- `deployment/azure/README.md`
- `deployment/aws/README.md`
- `docs/codex/reports/phase_21a_report.md`
- `docs/codex/reports/phase_21b_report.md`
- `docs/codex/reports/phase_21c_report.md`
- `docs/codex/reports/phase_21d_report.md`
- `docs/codex/reports/phase_21e_report.md`
- `docs/roadmap/README.md`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`

## 21. Backend validation results

**Final `python -m pytest -q --junitxml=.phase21f-full-final.xml`: 2681 passed, 0 failed, 0 skipped in 128.81s.** Includes all 94 PostgreSQL tests. Evidence: `.phase21f-full-final.log` and `.phase21f-full-final.xml`.

- Focused policy/parser/provider/storage run: **190 passed in 12.21s**.
- Application/API/attachment regression: **91 passed in 22.21s**.
- Final focused F container + parser regression: **41 passed in 1.51s**.
- Added PostgreSQL commit-failure regression: **1 passed in 0.63s** initially.
- Initial full suite: **2680 passed, 1 failed in 131.87s**. The runner incorrectly
  set global DATABASE_URL, violating a configuration test's absent-database
  premise. No production/test change made for it. Corrected runner removes
  DATABASE_URL, supplies only guarded ECI_POSTGRES_TEST_DATABASE_URL; focused
  failing test then passed (1 in 0.33s). Final full rerun recorded above.
- Sandboxed application run timed out after 45 seconds without output; authorized
  host execution passed, consistent with the prior documented TestClient issue.

## 22. PostgreSQL results

Initial whole PostgreSQL suite: **93 passed in 15.85s**. New commit-failure test
adds one case. Final full suite includes all 94 PostgreSQL tests. The targeted
kind migration round-trip runs on PostgreSQL and SQLite. Final CI-equivalent
upgrade → head assertion → downgrade base → empty assertion → re-upgrade → head
assertion: **PASS**, recorded in `.phase21f-ci-migrations.log`; database ends at `21d0001`. Only the dedicated guarded local database was touched.

## 23. Frontend results

`npm run test -- --run`: **369 passed across 30 files**, 20.39 s. Includes
attachment Analyze/history, safe hostile text, advisory labels, truncation,
concurrency/retry, BusinessContext, auth, workflow, and accessibility regression.
No frontend test was deleted or weakened. Existing layered backend defense tests
were retained; A/B gate-disabled tests explicitly monkeypatch the gate and do
not contradict current product enablement. Fixtures remain generated/synthetic;
no large workbook binary was added.

## 24. Lint/typecheck/build results

| Check | Result |
|---|---|
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm run build` | PASS; 334 modules |
| `npm ls --depth=0` | PASS |
| `python -m ruff check .` | PASS |
| `python -m pip check` | PASS; no broken requirements |
| `git diff --check` | PASS |
| `alembic heads` | One head: `21d0001` |
| TS/Pydantic tabular field comparison | MATCH |

Build retains the known non-blocking 667.54 kB JS chunk warning (185.52 kB gzip).
Non-blocking pip-cache/pyenv permission notices occurred. New import formatting
issues were corrected before final lint. No backend typecheck script is established.

## 25. Remaining limitations

- XLSX only, bounded sampling, heuristic first nonempty-row header inference;
  no formula calculation, charts/viewer/editor, or statistical completeness claim.
- Comments/hyperlink objects and embedded objects are ignored according to policy;
  formulas may appear only as inert strings. Unsafe external resources fail closed.
- Single-request memory probe cannot establish worst-case shared-string/style
  amplification, concurrent workload, or 0.5-vCPU latency. No load infrastructure
  added; verify bounded representative workbooks on both existing 1 GiB runtimes.
- Offline provider mocks establish contract parity, not live model quality/schema
  acceptance or prompt-injection immunity. Human review remains required.
- Real scanner/browser/mailbox/provider proof and cloud-specific artifacts are
  Phase 21G conditions. No local critical security/architecture issue is known.
- Frontend bundle warning remains. No claims of external-user acceptance or
  commercial production certification; Phase 17D remains deferred.

## 26. Phase 21G deployment requirements

Only after separate explicit authorization, preferably in a fresh Codex session
carrying this report and the preserved uncommitted tree:

1. Verify branch/HEAD/tree and actual Azure/AWS runtime/image/frontend/database/
   scanner state before repeating any operation. No automatic commit/push.
2. Follow established cloud build/deployment and migration runbooks; rebuild shared
   backend with openpyxl, verify one migration head and upgrade each independent
   database to `21d0001` before enabling the new backend/frontend. Preserve XLSX
   history; do not force downgrade. No new infrastructure or IAM expansion.
3. Build the proper frontend mode (`build:azure`, `build:aws`) with correct public
   API/auth configuration; verify serving revisions and health/readiness.
4. Validate owned Outlook/Graph → Azure/Foundry and Gmail → AWS/Bedrock XLSX flows:
   metadata list retrieves no bytes; explicit Analyze retrieves one; real scanner
   CLEAN precedes parser/AI; structured result persists and returns in history.
5. Exercise safe generated workbooks, truncation, inert formulas, unsupported
   legacy formats, normalized errors, ownership/Platform Owner isolation,
   PDF/DOCX/TXT regression and generic linked-context timeline. No Send or
   consequential business-state mutations; no EICAR unless separately authorized.
6. Verify live provider schema acceptance, latency, memory, timeout/error behavior
   and content-free operational logs on existing resource limits. Record measured
   evidence per cloud. Real-browser responsive/accessibility smoke remains needed.
7. Record closure evidence only after both clouds pass. Any stop/delete/resize or
   cost-management operation requires explicit instruction; do not infer it from
   historical runbooks.

Cloud resources touched: **No**. Live AI called: **No**. Phase 21G started: **No**.

## 27. Final readiness verdict

**PHASE 21F RESULT: PASS**

**READY FOR PHASE 21G WITH CONDITIONS**

| # | Readiness gate | Result |
|---|---|---|
| 1 | XLSX format policy | PASS |
| 2 | Scanner-before-parser | PASS |
| 3 | Container security | PASS |
| 4 | Formula non-execution | PASS |
| 5 | Bounded extraction | PASS |
| 6 | Bounded AI input | PASS |
| 7 | Prompt injection isolation | PASS — system/data separation; no action tools |
| 8 | Provider parity | PASS — offline contract |
| 9 | Structured persistence | PASS |
| 10 | Migration safety | PASS |
| 11 | Failure atomicity | PASS |
| 12 | Ownership isolation | PASS |
| 13 | Platform Owner non-bypass | PASS |
| 14 | API backward compatibility | PASS |
| 15 | Frontend safety | PASS |
| 16 | Truncation disclosure | PASS |
| 17 | BusinessContext non-invasive compatibility | PASS |
| 18 | Phase 22 boundary | PASS |
| 19 | Privacy/logging | PASS |
| 20 | Backend regression suite | PASS — 2681 |
| 21 | PostgreSQL suite | PASS — 94 |
| 22 | Frontend regression suite | PASS — 369 |
| 23 | Production builds | PASS — local frontend production build |
| 24 | CI readiness | PASS — existing jobs cover Phase 21 |
| 25 | No new infrastructure requirement | PASS |
| 26 | Azure deployment readiness | CONDITION — authorized deployment/live checks |
| 27 | AWS deployment readiness | CONDITION — authorized deployment/live checks |

Conditions resolvable during Phase 21G: actual deployment/migration state,
cloud-specific builds, real scanner and live provider/schema behavior, browser
flows, and memory/latency on both existing runtimes as specified in section 26.
Local blockers requiring repair before Phase 21G: **none identified**.
No cloud resource was touched and no live AI was called. No commit, push or
Phase 21G action. A fresh session is recommended for Phase 21G; preserve this
working tree and carry forward the explicit authorization boundary.
