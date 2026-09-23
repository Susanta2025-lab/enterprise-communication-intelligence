# Phase 21 — XLSX / Tabular Intelligence

## Status

| Slice | Status |
|---|---|
| Phase 21A — XLSX security policy & container foundation | **PASS** |
| Phase 21B — Bounded workbook extraction parser | **PASS** |
| Phase 21C — AI tabular analysis contract | **PASS** |
| Phase 21D — API / persistence integration (kind migration) | **PASS** |
| Phase 21E — Frontend workbook intelligence | **PASS** |
| Phase 21F — Hardening / docs / regression | **PASS — READY FOR PHASE 21G WITH CONDITIONS** |
| Phase 21G — Azure + AWS live validation / closure | **PASS — operator-reported manual validation; CLOSED for delivered XLSX scope** |

## Architecture locks (accepted)

See `docs/codex/reports/phase_21_readiness_assessment.md`,
`docs/codex/reports/phase_21a_report.md`,
`docs/codex/reports/phase_21b_report.md`, and
`docs/codex/reports/phase_21c_report.md`.

Initial support is `.xlsx` only via `openpyxl`, formulas never executed,
Phase 18 attachment path reused, no new infrastructure.

The A–C summaries below record historical gates; D enabled the current local product path. Phase 21 is CLOSED following operator-reported manual Azure/AWS validation recorded on 2026-09-23; evidence limits remain explicit below.

## Phase 21A summary

- Domain `AttachmentKind.XLSX` + OOXML/ZIP container validator
- Resource caps: 512 entries / 20 MiB uncompressed / 8 MiB part / 100:1 ratio
- Macros, encryption, external links/connections rejected
- Product Analyze remains fail-closed for XLSX (no retrieval/AI/persistence)
- `openpyxl>=3.1` added; no pandas; Alembic head unchanged at `20c0001`

## Phase 21B summary

- `parse_xlsx_attachment` / `extract_xlsx_workbook` with locked sheet/row/column/cell/character bounds
- Normalized `WorkbookExtraction` + deterministic text serialization
- Formulas inert; hyperlinks/external refs never followed; hidden sheets explicit
- `SafeAttachmentParser` dispatches XLSX; product Analyze still fail-closed
- No migration; Alembic head remains `20c0001`

## Phase 21C summary

- Provider-neutral `AIProvider.analyze_tabular` + `TabularAnalysisResult`
- Hard AI-input cap `XLSX_AI_INPUT_MAX_CHARS = 32_768` with explicit truncation
- Untrusted workbook fencing; Mock / Foundry / Bedrock offline parity
- Product Analyze still fail-closed; no persistence / migration / frontend

## Phase 21D summary

- Explicit XLSX Analyze preserves provenance/size → CLEAN scanner → container validation → parser/AI ordering.
- Complete validated `TabularAnalysisResult` persists in existing attachment history; legacy results remain nullable.
- Single migration `20c0001 → 21d0001` adds nullable JSONB and permits XLSX; downgrade refuses existing XLSX history.
- Ownership, advisory-only behavior, and no raw workbook persistence remain enforced.
- Full backend: **2663 passed**, including **93 PostgreSQL tests**; lint/dependency/whitespace checks pass.
- Audit and exact validation: [Phase 21D report](../codex/reports/phase_21d_report.md).

## Phase 21E summary

- Explicit XLSX Analyze uses the existing attachment endpoint; listing stays metadata-only.
- Typed tabular results render safe advisory sections, separate warnings/limitations, and visible bounded-sample disclosure.
- XLS/XLSM/XLSB/CSV/TSV remain unsupported; PDF/DOCX/TXT and mixed history remain compatible.
- Duplicate-request protection and generic BusinessContext timeline compatibility are covered.
- Frontend: **87 focused / 369 total tests passed**; typecheck, lint, production build, and whitespace checks pass.
- Focused backend API compatibility: **4 passed**; no backend changes, migration, cloud access, or live AI.
- Details and file inventory: [Phase 21E report](../codex/reports/phase_21e_report.md).

## Phase 21F summary

- Fixed semantic XML security bypasses, malformed ZIP error normalization, ambiguous/encrypted ZIP entries, and intermediate character-budget clipping; explicitly disabled openpyxl external-link retention.
- Full backend: **2681 passed**, including **94 PostgreSQL tests**; migration safety and CI full round-trip PASS, head `21d0001`.
- Frontend: **369 passed**; typecheck, lint, production build, ruff, pip check and whitespace checks PASS. Existing CI covers all additions.
- No dependencies, migrations, infrastructure or frontend features added in F. No cloud access or live AI.
- [Phase 21F report](../codex/reports/phase_21f_report.md) records the 27 gates, exact file inventory and remaining live-validation conditions.

## Phase 21G summary and closure

- Azure: PostgreSQL `21d0001`, Phase 21 backend and frontend deployed; `index-BQKDgcbq.js` hash matched; Outlook XLSX Analyze HTTP 200 via `microsoft_foundry`, structured history and truncation verified, final health/readiness HTTP 200.
- AWS: RDS `21d0001`, ECR `63669ec-p21g-20260923`, ECS `eci-api-dev:13`, frontend `index-BsxIj7rg.js` and hashes verified; Gmail XLSX Analyze via `amazon_bedrock`, truncation and saved history after reload verified; ECS COMPLETED (1 running, 0 pending), final health/readiness HTTP 200.
- Both cloud results are operator-reported manual evidence. The earlier failed Azure frontend upload is preserved in the [Phase 21G report](../codex/reports/phase_21g_report.md), followed by successful completion.
- Phase 21 is **CLOSED for the delivered XLSX scope**. Logs establish observed event ordering; source and integration tests support the stronger scanner-before-parser guarantee. Unsupported/security cases are not all tested live, and comprehensive memory/load/failure/accessibility validation is not supplied. See [evidence limitations](../codex/reports/phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations).

## Next

Stop at Phase 21 closure and Git commit preparation. Phase 22 requires a separate instruction; no commit, push or further cloud operation is authorized.

## Current security and release contract

Only `.xlsx` is supported; `.xls`, `.xlsm`, `.xlsb`, `.csv`, and `.tsv` fail closed.
Listing is metadata-only. Explicit Analyze follows ownership/provenance → one
retrieval → size/budget → CLEAN scanner → container/security validation → bounded
`openpyxl` extraction → bounded, untrusted AI sample → strict result validation →
existing `attachment_analyses` → typed API → escaped React text.

Formulas never execute; URLs are never followed. Macros, encryption, external
relationships, external workbook links and connections are rejected. Embedded
objects are warned about and ignored. Raw workbooks/XML/prompts/provider responses
are not persisted. Complete advisory `tabular_result` preserves separate warnings
and limitations. Potential dates/amounts/actions create no Phase 22 state.

Limits remain 5 MiB attachment; 512 ZIP entries; 20 MiB uncompressed total;
8 MiB per part; 100:1 compression ratio; 10 sheets; 50 columns/sheet;
100 data rows/sheet; 5,000 emitted cells; 200,000 extracted characters;
2,000 characters/cell; 32,768 workbook characters sent to AI.

Migration `21d0001` revises `20c0001`, permits XLSX and adds nullable JSONB
`tabular_result`. Downgrade refuses while XLSX history exists, before DDL.
Do not delete real XLSX history to force rollback: retain this revision or use
an explicitly approved data-retention/rollback plan. Test round-trips remove
synthetic rows only. Legacy PDF/DOCX/JPEG/PNG/TXT rows retain null tabular results.

Real scanner, live Foundry/Bedrock structured output and the reported browser/mailbox
flows passed Phase 21G manual validation. Full runtime memory/load/latency and
security-case coverage remain evidence limitations, not implied live passes.
No new infrastructure or IAM broadening is required by the implementation.
