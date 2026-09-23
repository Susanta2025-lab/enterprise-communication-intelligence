# Phase 21A — XLSX Security Policy & Container Foundation

> Historical slice report. Phase 21F reviews the combined A–E implementation; earlier fail-closed product gates and Alembic heads below describe that slice only. Current local XLSX Analyze is enabled, uses scanner-before-container/parser, and persists validated `tabular_result` at head `21d0001`. Subsequent Azure/AWS manual deployment and functional validation passed; see [Phase 21G closure and evidence limits](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations). See [the current roadmap](../../roadmap/phase-21-xlsx-tabular-intelligence.md).

## 1. Objective

Establish the secure XLSX identity and OOXML container-validation foundation so
a later Phase 21B bounded parser can receive only structurally acceptable
`.xlsx` workbooks. Product Analyze remains fail-closed for XLSX.

## 2. Baseline

| Fact | Value |
|---|---|
| Branch | `master` |
| HEAD | `63669ec8bdf27158817e4fe56858fd3df3ce3086` |
| Alembic head | `20c0001` (unchanged) |
| Assessment | `docs/codex/reports/phase_21_readiness_assessment.md` (preserved) |
| Verdict entering 21A | READY WITH CONDITIONS (locks accepted) |

## 3. Architecture locks applied

1. Initial format: `.xlsx` only
2. Parser family: `openpyxl` (dependency pinned; not used for extraction in 21A)
3. Formulas never executed (`data_only=False`, `read_only=True`, `keep_vba=False`)
4. Container bounds from assessment §9
5. Persistence model unchanged (`attachment_analyses`; no `xlsx` kind migration)
6. AI advisory-only; no AI invocation in 21A
7. Phase 18 attachment path reused (policy layer only)
8. Sync 1 GiB topology unchanged
9. No new infrastructure
10. `.xls` / `.xlsm` / `.xlsb` / `.csv` / `.tsv` fail closed

## 4. Files changed

### Created

- `docs/codex/reports/phase_21a_report.md`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`
- `tests/unit/domain/test_phase21a_xlsx_security.py`

### Modified

- `app/domain/enums.py` — `AttachmentKind.XLSX`
- `app/domain/attachment_policy.py` — XLSX policy, container validator, product gate
- `pyproject.toml` — `openpyxl>=3.1`
- `tests/unit/domain/test_enums.py`
- `tests/unit/domain/test_attachment_policy.py`
- `tests/unit/infrastructure/attachments/fixtures.py`
- `docs/roadmap/README.md`

### Preserved (not rewritten)

- `docs/codex/reports/phase_21_readiness_assessment.md`

## 5. Dependency change

| Package | Constraint | Notes |
|---|---|---|
| `openpyxl` | `>=3.1` | Pure Python; transitive `et_xmlfile` |
| pandas / calamine / LibreOffice | **not added** | |

Container/image impact: modest pure-Python wheel increase on `python:3.12-slim`.
No native binaries. No cloud deploy in 21A.

## 6. XLSX type policy

| Format | Policy |
|---|---|
| `.xlsx` + spreadsheet MIME + OOXML markers | Recognized internally; **product Analyze fail-closed** |
| `.xls` / `.xlsm` / `.xlsb` / `.csv` / `.tsv` | Rejected (rejected-extension / unsupported) |
| `application/octet-stream` as XLSX MIME | Rejected |

Identity requires **all** of:

1. Extension `.xlsx`
2. MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
3. ZIP magic (`PK`)
4. Members `[Content_Types].xml` and `xl/workbook.xml`
5. Not a DOCX polyglot (`word/document.xml` absent for XLSX; XLSX workbook absent for DOCX)

`xlsx_product_analysis_enabled()` returns `False`. Metadata pre-check rejects
XLSX before retrieval so end-user Analyze behavior stays fail-closed.

## 7. Container-validation architecture

```text
explicit Analyze
  → metadata policy (XLSX rejected — product gate)
  → (future) retrieve → scanner → validate_xlsx_container → Phase 21B parser
```

Public domain API:

- `validate_xlsx_container(payload) -> XlsxContainerValidationResult`
- `evaluate_attachment_content` validates XLSX when declared+detected match
- Result metadata only: recognized, sizes, member count, warnings

No cell/row/sheet extraction. No durable member writes.

## 8. ZIP-bomb / resource protections

| Limit | Value |
|---|---|
| Max attachment decoded bytes (outer) | 5 MiB (existing) |
| XLSX ZIP max entries | **512** |
| XLSX ZIP max uncompressed total | **20 MiB** |
| XLSX ZIP max single part | **8 MiB** |
| XLSX max compression ratio | **100:1** (defense-in-depth) |
| Path traversal / absolute member paths | Reject |

Inspection uses ZIP central-directory metadata only (no member extraction to disk).

## 9. Active / external-content policy

| Construct | 21A policy |
|---|---|
| `xl/vbaProject.bin` | **REJECT** |
| Macro-enabled Content_Types markers | **REJECT** |
| EncryptionInfo / EncryptedPackage | **REJECT** |
| `TargetMode="External"` relationships | **REJECT** |
| `xl/externalLinks/` | **REJECT** |
| `xl/connections.xml` | **REJECT** |
| `xl/embeddings/` | **WARN** `xlsx_embedded_object_ignored` (not opened) |
| Charts / styles / themes | Not inspected (ignored later) |

## 10. Formula non-execution guarantee

- No calculation engine introduced
- Domain constants: `OPENPYXL_READ_ONLY=True`, `OPENPYXL_DATA_ONLY=False`, `OPENPYXL_KEEP_VBA=False`
- Container validation does not import/use openpyxl
- Tests load formula workbooks with those settings and assert formula strings remain unevaluated
- Network access is not performed (socket monkeypatch coverage)

## 11. Error model

Failures use existing domain exceptions:

- `AttachmentUnsupportedError` — unsupported format, bad identity, macros, externals, ratio, member count
- `AttachmentExceedsLimitError` — uncompressed / single-part caps
- `AttachmentContentInvalidError` — size inconsistency (existing)

No workbook contents, member XML, paths, or stack traces in client-facing messages.

## 12. Observability / privacy

No new content logging. Validator result exposes only size/count/warning codes.
Existing attachment telemetry patterns unchanged. No cell/formula/filename dumps.

## 13. Tests added

Primary: `tests/unit/domain/test_phase21a_xlsx_security.py`

Coverage includes: valid containers, identity mismatches, unsupported spreadsheet
formats, ZIP limits, traversal, VBA/encryption/external links/connections,
embedded-object warning, formula non-execution, no-network, product fail-closed
metadata gate, DOCX↔XLSX discrimination.

## 14. Exact validation results

Recorded at Phase 21A completion (local offline, 2026-09-19):

| Check | Result |
|---|---|
| `tests/unit/domain/test_phase21a_xlsx_security.py` | **30 passed** |
| Focused attachment/domain suites (incl. 21A) | **139 passed** (earlier focused run) |
| Full `python -m pytest` | **2458 passed, 88 skipped** |
| `python -m ruff check .` | **All checks passed** |
| `python -m pip check` | **No broken requirements found** |
| `git diff --check` | **PASS** (no whitespace errors) |
| `openpyxl` installed | **3.1.5** (`>=3.1`) |
| Alembic head | **`20c0001`** (unchanged) |
| Migration created | **No** |

## 15. Known limitations

- Product Analyze still rejects XLSX pre-retrieval (intentional)
- No bounded cell extraction (Phase 21B)
- No AI / persistence / frontend / migration
- Compression-ratio cap is defense-in-depth (not an assessment KPI); may need tuning
- External hyperlink formulas inside cells are not scanned until 21B opens cells
- Embedded OLE allowed through container with warning only

## 16. Deferred Phase 21B work

- `parse_xlsx_attachment` with sheet/row/column/cell bounds
- Normalized tabular `extracted_text`
- Warnings for formulas present / truncation / hidden sheets
- Wire parser dispatch for `AttachmentKind.XLSX`
- Optionally flip `xlsx_product_analysis_enabled` only when integration slice is ready

## 17. Migration status

**No migration created.** Alembic head remains `20c0001`.
`ck_attachment_analyses_kind` still excludes `xlsx` (Phase 21D).

## 18. Cloud / infrastructure impact

None. No deploy. No Azure/AWS changes. Dependency-only image delta when images
are rebuilt later.

## 19. Final verdict

**PHASE 21A RESULT: PASS**
