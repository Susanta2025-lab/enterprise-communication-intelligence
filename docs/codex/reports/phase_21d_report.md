# Phase 21D audit and validation

> Historical slice report. Phase 21F reviews the combined A–E implementation; earlier fail-closed product gates and Alembic heads below describe that slice only. Current local XLSX Analyze is enabled, uses scanner-before-container/parser, and persists validated `tabular_result` at head `21d0001`. Subsequent Azure/AWS manual deployment and functional validation passed; see [Phase 21G closure and evidence limits](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations). See [the current roadmap](../../roadmap/phase-21-xlsx-tabular-intelligence.md).

PHASE 21D RESULT: PASS

Resumed the existing uncommitted Phase 21A–21D working tree on 2026-09-19.
Phase 21A, 21B, and 21C remain accepted work. No implementation was restarted.

## Audited behavior

- Explicit Analyze routes XLSX through the existing attachment service and history.
- Order remains retrieval/provenance → metadata/size gates → scanner → CLEAN → XLSX container validation → parser → tabular AI.
- Listing performs no content retrieval, container validation, parsing, or AI work.
- The complete validated `TabularAnalysisResult` survives save, detail, and list reads.
- PDF/DOCX/TXT retain `tabular_result=None`; legacy image kinds also remain supported.
- Ownership checks remain server-side, including Platform Owner isolation.
- Potential dates, amounts, and action mentions remain advisory text; no workflow,
  BusinessContext, deadline, obligation, or Phase 22 state is created by Analyze.
- Raw workbook bytes/XML, prompts, and raw provider responses are not persisted.

## Migration

Only the existing `alembic/versions/21d0001_attachment_analyses_kind_xlsx.py` is used.
Its parent is `20c0001`. It adds nullable PostgreSQL JSONB `tabular_result` and
allows `kind='xlsx'` in `ck_attachment_analyses_kind`. No additional migration.

The migration test verifies legacy row preservation, rejection of XLSX before
upgrade, successful `20c0001 → 21d0001` upgrade, complete result persistence,
refusal to downgrade while XLSX history exists without losing those rows,
successful `21d0001 → 20c0001` downgrade after removing only the synthetic XLSX
row, restoration of the old columns/constraint and legacy rows, then upgrade
to head and rejection of unsupported spreadsheet kinds. It runs on SQLite and
real PostgreSQL.

Reused `eci-phase21d-postgres`, bound to `127.0.0.1:55421`; initial database
revision was `21d0001`, with nullable JSONB and the XLSX kind constraint verified.
The PostgreSQL suite uses the repository's guarded disposable test database
fixtures, including their standard application-table truncation.

## Changes made during this resumed audit

- `app/application/services/attachment_analysis.py`: removed extra EOF blank line.
- `app/domain/schemas/tabular_analysis.py`: corrected re-export import formatting.
- `tests/unit/domain/test_phase21a_xlsx_security.py`: wrapped one long test signature.
- `tests/unit/infrastructure/attachments/test_xlsx_parser.py`: wrapped one long test signature.
- `tests/unit/infrastructure/storage/test_alembic.py`: extended the exact revision set and linear parent/head assertions to `21d0001`.
- `tests/unit/infrastructure/storage/test_models.py`: added only authorized `tabular_result` to the exact column allowlist; raw-content exclusions remain.
- `docs/roadmap/README.md` and `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`: update Phase 21D status.
- This report is new.

## Validation

Focused command (212 passed in 25.27s):

```sh
pytest -q \
  tests/unit/domain/test_phase21a_xlsx_security.py \
  tests/unit/domain/test_attachment_policy.py \
  tests/unit/infrastructure/attachments/test_xlsx_parser.py \
  tests/unit/providers/test_tabular_analysis_parity.py \
  tests/unit/providers/test_tabular_input.py \
  tests/unit/providers/test_tabular_output.py \
  tests/unit/providers/test_tabular_prompts.py \
  tests/integration/test_phase21d_xlsx_analysis.py \
  tests/unit/application/test_attachment_analysis.py \
  tests/unit/application/test_attachment_analysis_boundaries.py \
  tests/unit/application/test_attachment_inspection.py \
  tests/integration/test_mailbox_attachment_analysis.py \
  tests/unit/infrastructure/storage/test_attachment_analysis_repository.py \
  tests/unit/infrastructure/storage/test_phase21d_migration.py
```

`pytest -q tests/postgres`: **93 passed in 19.20s**, with the guarded local test
URL configured without printing or storing container credentials.

The initial sandboxed focused run stalled and was interrupted; the host rerun
passed. Host process inspection identified only this turn's focused pytest
process, with no older background pytest process remaining.

Initial full backend run: **2661 passed, 2 failed in 152.60s**. Both failures
were stale schema expectations in `test_alembic_revision_graph_is_valid` and
`test_attachment_analysis_columns_are_minimized`. Updated those expectations
for the authorized migration without relaxing the checks.

`pytest -q tests/unit/infrastructure/storage/test_alembic.py tests/unit/infrastructure/storage/test_models.py`:
**35 passed in 1.09s** after the fixes.

Final full backend command: `pytest -q --junitxml=.phase21d-full-final.xml`,
with `ECI_POSTGRES_TEST_DATABASE_URL` configured for the existing local container:
**2663 passed, 0 failed, 0 skipped in 148.02s**. This includes all 93 PostgreSQL tests.
Final database revision verified after the suite: **21d0001**.

- `alembic heads`: exactly one head, **21d0001**.
- `ruff check .`: **PASS**.
- `python -m pip check`: **PASS — No broken requirements found**.
  Pip emitted only a non-fatal cache-directory permission warning.
- `git diff --check`: **PASS**.

Local ignored validation artifacts: `.phase21d-focused-host.log`,
`.phase21d-postgres.log`, `.phase21d-full-final.log`, `.phase21d-full-final.xml`.
The initial run logs were retained too. No prior uncommitted work was discarded.

## Limitations and scope

- XLSX only; XLS/XLSM/XLSB/CSV/TSV remain unsupported.
- Extraction and AI input remain bounded; truncation is disclosed.
- Formulas are inert text and external workbook links are rejected.
- Downgrade intentionally refuses existing XLSX history rather than deleting it.
- Foundry and Bedrock coverage uses offline mocks, not live calls.
- No Azure/AWS resources touched, deployment, commit, or push.
- No frontend changes or Phase 21E work.

## Working-tree file inventory
This inventory includes preserved Phase 21A–21C work and the existing Phase 21D
implementation; it is not a claim that every file was changed during this audit.

### Modified tracked files
- `tests/unit/infrastructure/storage/test_alembic.py`
- `tests/unit/infrastructure/storage/test_models.py`
- `app/application/services/attachment_analysis.py`
- `app/application/services/attachment_analysis_history.py`
- `app/application/services/attachment_inspection.py`
- `app/application/services/communication_analysis.py`
- `app/domain/attachment_policy.py`
- `app/domain/enums.py`
- `app/domain/exceptions.py`
- `app/domain/interfaces/ai_provider.py`
- `app/domain/interfaces/attachment_analysis_repository.py`
- `app/domain/models/__init__.py`
- `app/domain/models/attachment.py`
- `app/domain/schemas/__init__.py`
- `app/infrastructure/attachments/parser.py`
- `app/infrastructure/storage/models.py`
- `app/infrastructure/storage/repositories/attachment_analysis.py`
- `app/providers/amazon_bedrock/output.py`
- `app/providers/amazon_bedrock/provider.py`
- `app/providers/common/prompts.py`
- `app/providers/microsoft_foundry/output.py`
- `app/providers/microsoft_foundry/provider.py`
- `app/providers/mock/provider.py`
- `app/schemas/attachments.py`
- `docs/roadmap/README.md`
- `pyproject.toml`
- `tests/support/in_memory_persistence.py`
- `tests/unit/application/test_attachment_analysis.py`
- `tests/unit/domain/test_attachment_policy.py`
- `tests/unit/domain/test_enums.py`
- `tests/unit/infrastructure/attachments/fixtures.py`
- `tests/unit/infrastructure/attachments/test_parser_dispatcher.py`
- `tests/unit/infrastructure/storage/test_attachment_analysis_repository.py`

### New untracked files
- `AGENTS.md`
- `alembic/versions/21d0001_attachment_analyses_kind_xlsx.py`
- `app/domain/models/tabular_analysis.py`
- `app/domain/models/workbook_extraction.py`
- `app/domain/schemas/tabular_analysis.py`
- `app/infrastructure/attachments/xlsx.py`
- `app/providers/common/tabular_input.py`
- `app/providers/common/tabular_output.py`
- `app/providers/common/tabular_prompts.py`
- `docs/codex/reports/phase_21_readiness_assessment.md`
- `docs/codex/reports/phase_21a_report.md`
- `docs/codex/reports/phase_21b_report.md`
- `docs/codex/reports/phase_21c_report.md`
- `docs/codex/reports/phase_21d_report.md`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`
- `tests/integration/test_phase21d_xlsx_analysis.py`
- `tests/postgres/test_phase21d_xlsx.py`
- `tests/unit/domain/test_phase21a_xlsx_security.py`
- `tests/unit/infrastructure/attachments/test_xlsx_parser.py`
- `tests/unit/infrastructure/storage/test_phase21d_migration.py`
- `tests/unit/providers/test_tabular_analysis_parity.py`
- `tests/unit/providers/test_tabular_input.py`
- `tests/unit/providers/test_tabular_output.py`
- `tests/unit/providers/test_tabular_prompts.py`

## Selected final-suite test counts

| Test module | Passed |
|---|---:|
| `tests/integration/test_phase21d_xlsx_analysis.py` | 43 |
| `tests/postgres/test_attachment_analysis_repository.py` | 3 |
| `tests/postgres/test_phase21d_xlsx.py` | 5 |
| `tests/unit/domain/test_phase21a_xlsx_security.py` | 30 |
| `tests/unit/infrastructure/attachments/test_xlsx_parser.py` | 26 |
| `tests/unit/infrastructure/storage/test_attachment_analysis_repository.py` | 9 |
| `tests/unit/infrastructure/storage/test_phase21d_migration.py` | 1 |
| `tests/unit/providers/test_tabular_analysis_parity.py` | 15 |
| `tests/unit/providers/test_tabular_input.py` | 6 |
| `tests/unit/providers/test_tabular_output.py` | 6 |
| `tests/unit/providers/test_tabular_prompts.py` | 11 |
