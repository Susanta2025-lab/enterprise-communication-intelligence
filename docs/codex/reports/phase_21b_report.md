# Phase 21B — Bounded XLSX Workbook Extraction

> Historical slice report. Phase 21F reviews the combined A–E implementation; earlier fail-closed product gates and Alembic heads below describe that slice only. Current local XLSX Analyze is enabled, uses scanner-before-container/parser, and persists validated `tabular_result` at head `21d0001`. Subsequent Azure/AWS manual deployment and functional validation passed; see [Phase 21G closure and evidence limits](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations). See [the current roadmap](../../roadmap/phase-21-xlsx-tabular-intelligence.md).

## 1. Objective

Add a secure, bounded, deterministic XLSX workbook extractor that consumes only
Phase 21A-validated `.xlsx` containers and produces a provider-neutral
normalized tabular sample suitable for later Phase 21C AI fencing.

Product Analyze remains fail-closed for XLSX after this slice.

## 2. Baseline

| Fact | Value |
|---|---|
| Branch | `master` |
| HEAD entering 21B | `63669ec8bdf27158817e4fe56858fd3df3ce3086` |
| Alembic head | `20c0001` (unchanged) |
| Phase 21A | PASS |
| Readiness | READY WITH CONDITIONS (locks accepted) |

## 3. Phase 21A contract consumed

- `validate_xlsx_container()` must succeed before openpyxl load
- `OPENPYXL_READ_ONLY=True`, `OPENPYXL_DATA_ONLY=False`, `OPENPYXL_KEEP_VBA=False`
- Container rejects macros, encryption, external links/connections
- `xlsx_product_analysis_enabled()` remains `False`
- `_PRODUCT_ANALYSIS_KINDS` excludes XLSX

## 4. Parser architecture

```text
XLSX bytes
  → validate_xlsx_container()          # Phase 21A
  → openpyxl load_workbook(read_only, data_only=False, keep_vba=False)
  → bounded sheet / row / column / cell / character traversal
  → WorkbookExtraction (structured)
  → serialize → ParsedAttachment.extracted_text
```

Layers:

| Component | Layer | Role |
|---|---|---|
| `WorkbookExtraction` / `SheetExtraction` | Domain models | Provider-neutral normalized representation |
| Extraction caps | `attachment_policy` | Locked limits + cell-char safeguard |
| `parse_xlsx_attachment` / `extract_xlsx_workbook` | Infrastructure | openpyxl isolation |
| `SafeAttachmentParser` | Infrastructure | Kind dispatch includes XLSX |

No FastAPI, mailbox, persistence, AI, BusinessContext, or workflow coupling.

## 5. Normalized workbook model

`WorkbookExtraction`:

- `kind=xlsx`, `version=1`
- `sheet_count`, `sheets_processed`, `sheets_skipped`
- `sheets: tuple[SheetExtraction, ...]`
- `warnings`, `truncated`, `truncation_reasons`
- `cells_emitted`, `characters_emitted`

`SheetExtraction`:

- `name`, `visibility` (`visible` / `hidden` / `very_hidden`)
- inferred header + sampled data rows (plain-text cell tuples)
- processed row/column/cell counts
- truncation reasons; optional skip metadata
- source `max_row` / `max_column` hints only (never used for allocation)

Serialization is deterministic plain text for the existing `attachment_texts`
channel (Phase 21C will fence it as untrusted).

## 6. Exact extraction limits

From readiness assessment §9 (locked):

| Limit | Value |
|---|---|
| Max sheets processed | **10** |
| Max columns per sheet | **50** |
| Max sampled data rows per sheet (excl. header) | **100** |
| Max total cells emitted | **5_000** |
| Max extracted text characters | **200_000** (existing `MAX_EXTRACTED_TEXT_CHARS`) |

Implementation safeguard (not §9-locked; subordinate to 200_000):

| Limit | Value |
|---|---|
| Max per-cell characters | **2_000** (`XLSX_MAX_CELL_CHARS`) |

ZIP envelope remains Phase 21A (512 / 20 MiB / 8 MiB / 100:1).

## 7. Sheet policy

- Sheets processed in workbook order
- Visible, hidden, and very-hidden sheets are all processed within the sheet cap
- Visibility is explicit in structured + serialized output
- Warning `xlsx_hidden_sheets_present` when any non-visible sheet is processed
- Sheets beyond the cap are recorded as skipped with `xlsx_truncated_sheets`
- Empty sheets emit no cells; workbooks with zero emitted cells raise
  `AttachmentNoExtractableTextError`
- Workbook state is never mutated (no unhide)

## 8. Cell normalization policy

Deterministic rendering:

| Input | Output |
|---|---|
| string | as text (NUL stripped) |
| int | decimal string |
| float / Decimal | locale-independent numeric text |
| bool | `true` / `false` |
| date | ISO `YYYY-MM-DD` |
| datetime | ISO without microseconds |
| time | ISO time |
| blank / None / EmptyCell | omitted (empty placeholder inside row width) |
| Excel errors (`#REF!`, …) | literal error text |
| formulas | `formula:=...` (inert) |

No business-semantic reinterpretation of string dates like `01/02/2027`.

## 9. Formula policy

- `data_only=False` — formulas remain strings
- Never evaluated; no calculation engine
- Warning `xlsx_formulas_present`
- `=HYPERLINK(...)` → warning `xlsx_hyperlink_formula`; URL not fetched
- External workbook refs in formula text → warning `xlsx_external_reference`; no fetch
- Prompt-injection-like formula/cell text preserved as data

## 10. Hyperlink / external-resource behavior

- No HTTP / socket I/O from workbook contents
- Package-level external relationships still rejected by Phase 21A
- Read-only mode does not expose cell hyperlink objects; they are omitted
- `HYPERLINK` formulas retained as inert labeled text only

## 11. Truncation model

Stable reasons (`XlsxTruncationReason`):

- `xlsx_truncated_sheets`
- `xlsx_truncated_rows`
- `xlsx_truncated_columns`
- `xlsx_truncated_cells`
- `xlsx_truncated_characters`
- `xlsx_truncated_cell_chars`

`ParsedAttachment.truncated=true` whenever sampling occurred. Serialized output
also lists truncation reasons. Full-workbook coverage is never implied when
truncated.

## 12. Memory / performance safeguards

- `read_only=True` streaming iteration
- Explicit `max_row` / `max_col` on `iter_rows` (never allocate from declared dims)
- Declared dimensions used only as truncation hints
- Empty cells skipped; no full sparse matrix materialization
- Global cell + character caps stop workbook traversal early
- No pandas; no workbook rewrite/save

## 13. Error / privacy behavior

| Condition | Error |
|---|---|
| Fails Phase 21A container validation | `AttachmentUnsupportedError` |
| openpyxl load / traversal failure | `AttachmentParseError` |
| Zero extractable cells | `AttachmentNoExtractableTextError` |

Client-facing messages remain generic. No cell values, formulas, sheet XML,
paths, or stack traces are logged by the parser.

## 14. Files created

- `app/domain/models/workbook_extraction.py`
- `app/infrastructure/attachments/xlsx.py`
- `tests/unit/infrastructure/attachments/test_xlsx_parser.py`
- `docs/codex/reports/phase_21b_report.md`

## 15. Files modified

- `app/domain/attachment_policy.py` — extraction cap constants
- `app/domain/models/__init__.py` — export workbook models
- `app/infrastructure/attachments/parser.py` — XLSX dispatch
- `tests/unit/infrastructure/attachments/fixtures.py` — `xlsx_workbook` helper
- `tests/unit/infrastructure/attachments/test_parser_dispatcher.py`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`
- `docs/roadmap/README.md` — Phase 21 status line only

## 16. Tests

Primary: `tests/unit/infrastructure/attachments/test_xlsx_parser.py`

Coverage: basic values/types, multi-sheet, empty, formulas/HYPERLINK/external
ref, prompt-injection text, hidden/very-hidden, merged, sparse, wide, sheet/row/
column/cell/char bounds, Phase 21A gate, no-network, product fail-closed,
dispatcher routing, PDF regression.

## 17. Full validation results

Recorded at Phase 21B completion (local offline, 2026-09-19):

| Check | Result |
|---|---|
| `tests/unit/infrastructure/attachments/test_xlsx_parser.py` | **26 passed** |
| `tests/unit/infrastructure/attachments/test_parser_dispatcher.py` | **3 passed** (incl. XLSX route) |
| Focused attachment/domain suites | **137 passed** |
| Full `python -m pytest` | **2485 passed, 88 skipped** |
| `python -m ruff check .` | **All checks passed** |
| `python -m pip check` | **No broken requirements found** |
| `git diff --check` | **PASS** |
| Alembic head | **`20c0001`** (unchanged) |
| Migration created | **No** |
| `xlsx_product_analysis_enabled()` | **False** |
| XLSX in `_PRODUCT_ANALYSIS_KINDS` | **False** |

## 18. Known limitations

- Comments/notes ignored (openpyxl `read_only` does not expose them)
- Cell hyperlink objects omitted in read-only mode (formula hyperlinks covered)
- Styles, charts, drawings, pivot caches ignored
- Header inference is first non-empty row (heuristic, labeled)
- Soft ~32–64 KiB AI payload preference not hard-enforced; hard stop remains 200_000
- Product Analyze still rejects XLSX pre-retrieval (intentional)
- No AI / persistence / frontend / kind-constraint migration

## 19. Database / migration status

**No migration.** Alembic head remains `20c0001`.
`ck_attachment_analyses_kind` still excludes `xlsx` (Phase 21D).

## 20. Product-path status

Fail-closed preserved:

- `_PRODUCT_ANALYSIS_KINDS` excludes XLSX
- `xlsx_product_analysis_enabled()` → `False`
- Metadata pre-check rejects XLSX before retrieval
- No XLSX persistence path enabled
- No AI invocation added for XLSX in the product flow

Parser dispatch supports XLSX only for already-validated bytes (unit/direct use).

## 21. Deferred Phase 21C work

- Prompt wording for spreadsheet/tabular untrusted fencing
- Mock / Foundry / Bedrock offline parity for `kind=xlsx`
- Injection fixture asserting no send/workflow/BusinessContext mutation
- Optional soft payload sizing guidance in AI request shaping

## 22. Final verdict

**PHASE 21B RESULT: PASS**
