# Phase 21C — XLSX AI Contract, Prompt Fencing & Provider Parity

> Historical slice report. Phase 21F reviews the combined A–E implementation; earlier fail-closed product gates and Alembic heads below describe that slice only. Current local XLSX Analyze is enabled, uses scanner-before-container/parser, and persists validated `tabular_result` at head `21d0001`. Subsequent Azure/AWS manual deployment and functional validation passed; see [Phase 21G closure and evidence limits](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations). See [the current roadmap](../../roadmap/phase-21-xlsx-tabular-intelligence.md).

## 1. Objective

Add a provider-neutral, fail-closed XLSX/tabular AI analysis contract that
consumes Phase 21B bounded workbook samples, fences them as untrusted data,
enforces a hard AI-input cap, validates bounded structured output, and
implements identical logical behavior on Mock, Microsoft Foundry, and Amazon
Bedrock — without enabling product Analyze, persistence, or cloud live calls.

## 2. Baseline

| Fact | Value |
|---|---|
| Branch | `master` |
| HEAD entering 21C | `63669ec8bdf27158817e4fe56858fd3df3ce3086` |
| Alembic head | `20c0001` (unchanged) |
| Phase 21A | PASS |
| Phase 21B | PASS |
| Readiness | READY WITH CONDITIONS |

## 3. Phase 21A/21B contracts consumed

- Phase 21A: `validate_xlsx_container`, formula non-execution locks, product gate
- Phase 21B: `WorkbookExtraction` / `serialize_workbook_extraction` /
  `ParsedAttachment.extracted_text` with parser caps (200_000 chars / 5_000 cells)
- Product Analyze remains fail-closed (`xlsx_product_analysis_enabled() == False`)

## 4. AI architecture

Reuses the Phase 20 specialized-provider pattern (`suggest_business_context`),
not a parallel AI framework:

```text
WorkbookExtraction / serialized text
  → prepare_tabular_analysis_request*(...)   # hard AI-input bound
  → TabularAnalysisRequest
  → AIProvider.analyze_tabular(...)
       Mock | MicrosoftFoundry | AmazonBedrock
  → parse_tabular_analysis_output → TabularAnalysisResult
```

No FastAPI route, no persistence, no AttachmentAnalysisService wiring in 21C.

## 5. Provider-neutral output model

`TabularAnalysisResult` (domain schema):

| Field | Role |
|---|---|
| `summary` | Concise advisory workbook summary |
| `sheet_summaries` | Per-sheet advisory summaries |
| `important_fields` | Likely important columns/headers |
| `notable_values_or_patterns` | Visible patterns (not statistical anomaly claims) |
| `data_quality_observations` | Missing/inconsistent/duplicated-looking values |
| `potential_dates` | Advisory date observations (not deadlines) |
| `potential_amounts` | Advisory amount observations |
| `potential_action_mentions` | Advisory action-like text (not workflow actions) |
| `warnings` / `limitations` | Safety / completeness disclosure |
| `source_truncated` | Explicit truncation flag |
| `provider` | Opaque provider id |

## 6. AI input bound

| Cap | Value | Rationale |
|---|---|---|
| `XLSX_AI_INPUT_MAX_CHARS` | **32_768** | Smallest practical lock in readiness §9 preferred 32–64 KiB range; character-based (matches ECI extract convention); UTF-8-safe via Python `str` slicing; strictly below parser 200_000 |

Enforced in `prepare_tabular_analysis_request` / `_from_text` **before** provider
invocation. Truncation prefers sheet/row boundaries, emits
`xlsx_ai_input_truncated` + `[AI_INPUT_TRUNCATED]`, and sets
`source_truncated=true`. Same cap for Mock/Foundry/Bedrock. No multi-call split.

## 7. AI output bounds

| Field | Max items | Max string length |
|---|---|---|
| `summary` | 1 | 2_000 |
| `sheet_summaries` | 10 | name 200 / summary 500 |
| `important_fields` | 20 | 200 |
| `notable_values_or_patterns` | 20 | 300 |
| `data_quality_observations` | 15 | 300 |
| `potential_dates` | 15 | 200 |
| `potential_amounts` | 15 | 200 |
| `potential_action_mentions` | 15 | 300 |
| `warnings` | 20 | 200 |
| `limitations` | 10 | 300 |

Domain models use `extra="forbid"`. Mapper truncates excessive LLM lists/strings.

## 8. Prompt-fencing architecture

Dedicated prompts (mirroring context-suggestion):

- System: `TABULAR_ANALYSIS_SYSTEM_PROMPT` (trusted policy only)
- User: `build_tabular_analysis_user_prompt` with fences:

```text
----- BEGIN UNTRUSTED WORKBOOK DATA -----
...workbook sample only...
----- END UNTRUSTED WORKBOOK DATA -----
```

Workbook content never enters system instructions. Existing communication
`SYSTEM_PROMPT` also notes spreadsheet cells/formulas/sheet names are untrusted
when present on the attachment_texts path.

## 9. Prompt-injection protections

Hostile cell/header/sheet-name/formula/URL text remains inside the untrusted
fence and is preserved as source data. It cannot become system instructions.
Tests cover ignore/admin/secrets/send/approve/URL/schema-break/formula cases.
No network, workflow, or state mutation from workbook content.

## 10. Mock provider implementation

`MockAIProvider.analyze_tabular`:

- Deterministic advisory result from workbook text heuristics
- Honors request truncation
- Supports `tabular_result` / `tabular_error` test injection
- Existing `analyze` / suggestion behavior unchanged

## 11. Foundry implementation

`MicrosoftFoundryProvider.analyze_tabular` (offline code only):

- `instructions=TABULAR_ANALYSIS_SYSTEM_PROMPT`
- `input=build_tabular_analysis_user_prompt(request)`
- Strict JSON schema `FOUNDRY_TABULAR_ANALYSIS_JSON_SCHEMA`
- Shared parse/map path; normalized errors; no content logging

## 12. Bedrock implementation

`AmazonBedrockProvider.analyze_tabular` (offline code only):

- Converse system/user with same prompt semantics
- `BEDROCK_TABULAR_ANALYSIS_JSON_SCHEMA`
- Shared parse/map path; same bounds; normalized errors

## 13. Provider-parity results

Offline parity tests in `test_tabular_analysis_parity.py` confirm Mock/Foundry/
Bedrock share:

- same request fencing / system prompt
- same result model fields
- truncation forced from request
- malformed/empty/prose/invalid shape rejection
- provider error propagation
- injection isolation
- inert formulas / no network

## 14. Error handling

- Empty / malformed / schema-mismatch → `TabularAnalysisOutputError`
- Bedrock empty Converse text → `BedrockOutputError` (existing pattern)
- Provider transport failures re-raised after structured failure logs
- Default `AIProvider.analyze_tabular` → `TabularAnalysisUnsupportedError`

## 15. Privacy/logging

Safe metadata only: provider, operation, `input_character_count`,
`source_truncated`, sheet_summary_count, duration, `error_class`.

Not logged: cell values, formulas, workbook text, prompt bodies, raw responses.

## 16. Phase 22 boundary

`potential_*` fields are advisory text only. No Deadline / Obligation /
WorkItem / ActionItem domain entities created or persisted.

## 17. BusinessContext boundary

No BusinessContext mutation, no context id on the tabular contract, no
automatic matter selection. Phase 20 code untouched.

## 18. Files created

- `app/domain/schemas/tabular_analysis.py`
- `app/providers/common/tabular_input.py`
- `app/providers/common/tabular_prompts.py`
- `app/providers/common/tabular_output.py`
- `tests/unit/providers/test_tabular_input.py`
- `tests/unit/providers/test_tabular_prompts.py`
- `tests/unit/providers/test_tabular_output.py`
- `tests/unit/providers/test_tabular_analysis_parity.py`
- `docs/codex/reports/phase_21c_report.md`

## 19. Files modified

- `app/domain/attachment_policy.py` — `XLSX_AI_INPUT_MAX_CHARS`
- `app/domain/exceptions.py` — `TabularAnalysisUnsupportedError`
- `app/domain/interfaces/ai_provider.py` — `analyze_tabular`
- `app/domain/schemas/__init__.py` — exports
- `app/providers/common/prompts.py` — spreadsheet untrusted note
- `app/providers/mock/provider.py` — tabular contract
- `app/providers/microsoft_foundry/{provider,output}.py`
- `app/providers/amazon_bedrock/{provider,output}.py`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`
- `docs/roadmap/README.md` — Phase 21 status line only

## 20. Dependency changes

**None.** No new LLM libraries, pandas, or tokenizers.

## 21. Tests/results

Recorded at Phase 21C completion (local offline, 2026-09-19):

| Check | Result |
|---|---|
| Phase 21C focused tests (`test_tabular_*.py`) | **38 passed** |
| Provider + attachment regression | **277 passed** |
| Full `python -m pytest` | **2523 passed, 88 skipped** |
| `python -m ruff check .` | **All checks passed** |
| `python -m pip check` | **No broken requirements found** |
| `git diff --check` | **PASS** |
| Type checker | Not configured in repository |
| Alembic head | **`20c0001`** (unchanged) |
| `xlsx_product_analysis_enabled()` | **False** |
| `XLSX_AI_INPUT_MAX_CHARS` | **32_768** |

## 22. Product-path status

Fail-closed preserved:

- `_PRODUCT_ANALYSIS_KINDS` excludes XLSX
- `xlsx_product_analysis_enabled()` → `False`
- No product Analyze → tabular AI wiring
- No API / frontend enablement

## 23. Migration status

**No migration.** Alembic head remains `20c0001`.
`ck_attachment_analyses_kind` still excludes `xlsx` (Phase 21D).

## 24. Known limitations

- Tabular AI is an internal provider contract only (not product-integrated)
- Soft parser sample may still exceed AI cap; AI prep truncates further
- Mock heuristics are deterministic stubs, not LLM-quality summaries
- No live Foundry/Bedrock invocation in this slice
- Header inference remains Phase 21B heuristic

## 25. Deferred Phase 21D work

- Alembic revision to allow `kind='xlsx'`
- Wire product Analyze path (inspect → parse → tabular or attachment AI)
- Persist `attachment_analyses` rows for XLSX
- History/read API coverage
- Keep frontend to Phase 21E

## 26. Final verdict

**PHASE 21C RESULT: PASS**
