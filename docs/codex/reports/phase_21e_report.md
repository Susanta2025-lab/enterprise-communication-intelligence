# Phase 21E — XLSX Frontend Product Experience

> Historical slice report. Phase 21F reviews the combined A–E implementation; earlier fail-closed product gates and Alembic heads below describe that slice only. Current local XLSX Analyze is enabled, uses scanner-before-container/parser, and persists validated `tabular_result` at head `21d0001`. Subsequent Azure/AWS manual deployment and functional validation passed; see [Phase 21G closure and evidence limits](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations). See [the current roadmap](../../roadmap/phase-21-xlsx-tabular-intelligence.md).

## 1. Objective

Expose the accepted Phase 21D XLSX backend through the existing attachment UI,
with explicit Analyze, structured advisory results, visible sampling disclosure,
safe text rendering, and backwards-compatible history. Phase 21E only.

## 2. Baseline

Verified before editing on 2026-09-19:

- Branch: `master`.
- HEAD: `63669ec8bdf27158817e4fe56858fd3df3ce3086`.
- `git status --short`: existing uncommitted Phase 21A–21D backend, migration,
  tests, reports, roadmap, and validation artifacts; no frontend changes.
- `alembic heads`: exactly one head, `21d0001` (read-only graph inspection).
- Read AGENTS.md, README.md, readiness assessment, Phase 21A–21D reports,
  and the Phase 21 roadmap. Earlier reports describe their historical gates;
  actual Phase 21D schemas and services confirm XLSX is enabled.
- All prior work was preserved. No reset, revert, stash, clean, checkout,
  commit, push, migration operation, or database operation was performed.

## 3. Backend contract consumed

Inspected `app/schemas/attachments.py` and
`app/domain/models/tabular_analysis.py`, plus the existing attachment routes,
service, and client. The existing POST
`/api/v1/connector-accounts/{id}/messages/attachments/analyze` accepts only
`provider_message_id` and `provider_attachment_id`.

Analyze, history list, and history detail share `AttachmentAnalysisResponse`.
It now allows `kind="xlsx"` and nullable `tabular_result`, already implemented
by Phase 21D. The frontend consumes this contract without backend changes.

## 4. Frontend architecture

Existing React/TypeScript/Vite SPA, Tailwind styling, handwritten API contracts,
`EciApiClient`, TanStack Query metadata/history queries, and explicit
`useAnalyzeAttachment` request state remain in use. No generated-schema system
exists for these contracts. `AttachmentsSection` → `AttachmentItem` →
`AttachmentAnalysisPanel` now delegates structured results to one small
`TabularAnalysisPanel`. Routing is unchanged.

## 5. API/type changes

`AttachmentKind` adds `"xlsx"`.
`AttachmentAnalysisResponse` adds
`tabular_result?: TabularAnalysisResult | null`.

`TabularSheetSummary` contains `sheet_name: string` and `summary: string`.
`TabularAnalysisResult` contains:

- `summary: string`
- `sheet_summaries: readonly TabularSheetSummary[]`
- readonly string arrays: `important_fields`, `notable_values_or_patterns`,
  `data_quality_observations`, `potential_dates`, `potential_amounts`,
  `potential_action_mentions`, `warnings`, `limitations`
- `source_truncated: boolean`
- `provider?: string | null`

The server serializes defaulted lists and sheet names; only the outer result
and provider are optional in the TypeScript response. A local read-only
assertion compared both TypeScript field sets with the Pydantic models: PASS.
The existing typed client methods automatically consume these additive types.

## 6. Supported-format UX

XLSX displays **Excel workbook (.xlsx)** and an XLSX text icon. PDF/DOCX/TXT
remain analyzable. XLS/XLSM/XLSB/CSV/TSV remain unsupported, including when
misdeclared as `text/plain` or XLSX MIME. Known unsupported spreadsheet MIME
types also fail the display policy before supported-type fallback.

JPEG/PNG retain their existing provider-capability gate. Frontend metadata
classification remains a display aid; the backend authoritatively checks
extension/MIME/content, size, scanner, and parser safety.

## 7. Analyze flow

Listing and history perform only existing metadata/result GETs. Explicit
keyboard or pointer Analyze makes the existing single-attachment POST. No
background Analyze, raw-byte GET, workbook preview, download, or browser parser
was added. The existing history query is invalidated after success.

A synchronous in-flight guard prevents same-tick duplicate requests. Analyze
controls for sibling attachments are disabled while the selected message has
an in-flight attachment request, matching the hook's single pending ID.
Navigation resets the request scope; an old response cannot populate the new
message's panel or clear its pending request. Explicit requests on a different
message can proceed; navigation does not cancel a backend operation.

## 8. Tabular-result UI

Concise stacked sections render workbook summary, sheet summaries, important
fields, notable values/patterns, data-quality observations, potential dates,
potential amounts, potential action mentions, warnings, and limitations.
Empty collections omit their sections. Empty sheet names use “Unnamed sheet”.

Structured results replace the legacy summary/priority/category/action-items
body; ordinary attachment results retain that body. Backend attachment-level
warnings and tabular warnings are deduplicated within Warnings. Limitations
remain a separate section. Provider follows the existing subdued metadata
convention, with the tabular provider as fallback; no vendor branding added.

## 9. Truncation UX

When `tabular_result.source_truncated` or the attachment's `truncated` is true,
a visible bordered status near the top says:

> Analysis used a bounded sample of this workbook.

No frontend copy claims complete-workbook coverage. Detailed backend warnings
and limitations remain visible. Tests cover both flags independently and
combined, including source truncation while attachment truncation is false.

## 10. Advisory semantics

The UI states that AI observations are advisory and require review. Potential
dates, amounts, and action mentions retain those labels. They are not rendered
as deadlines, amounts due, tasks, or workflow actions. No new action, payment,
calendar, approval, obligation, BusinessContext assignment, or Send control.

## 11. Safety/escaping

All workbook-derived values use ordinary React text interpolation. No HTML
injection, markdown interpreter, formula execution, automatic URL linking,
network navigation, workbook parsing, or new content logging was introduced.

Tests place script tags, image/onerror markup, javascript URLs, HYPERLINK
formulas, HTTPS URLs, and instruction-like payment text in every tabular text
field, including sheet names and provider metadata. Values remain text; no
script/image/link/form/input/button is created in the result and no alert runs.
A source scan found no `dangerouslySetInnerHTML` in mailbox components.

## 12. Error/loading behavior

Existing `EciApiClient` error classification and `ProductErrorState` provide
controlled copy and focus handling for unsupported formats, invalid content,
security/scanner rejection, oversized files, parser failure, scanner/provider
unavailability, malformed AI output, authorization/not-found, and generic
errors. No backend detail, stack trace, workbook XML, or provider output is
shown. No spreadsheet-specific error taxonomy was added.

Pending text uses `role="status"`; the selected Analyze button has `aria-busy`
and is disabled. Retry uses existing explicit controls, clears the prior error,
and cannot run a parallel request in the same message. No automatic AI retry.

## 13. History compatibility

Current and previous XLSX analyses reuse `AttachmentAnalysisPanel`, including
sampling disclosures. Mixed legacy history and `tabular_result=null` or omitted
remain valid. PDF/DOCX/TXT regression tests verify unchanged legacy output.
History reads do not Analyze or retrieve bytes. No history redesign.

## 14. BusinessContext compatibility

The existing timeline renders `attachment_analysis_completed` using generic
title, summary, and timestamp fields. An XLSX fixture verifies this display
without attachment requests or POSTs. No BusinessContext production code,
ownership rules, association behavior, or timeline semantics changed.

## 15. Accessibility considerations

Existing native buttons remain keyboard accessible. Structured sections have
semantic headings and accessible names; collections use lists. Sampling is
conveyed with text and a status role, not color alone. Error focus behavior is
retained. Automated axe coverage passes for the structured result. Stacked
sections and word wrapping fit the current narrow layout without a grid or
wide table. Real-browser responsive/screen-reader validation is not claimed.

## 16. Files created

- `frontend/src/components/mailbox/TabularAnalysisPanel.tsx`
- `frontend/src/test/tabularAnalysis.test.tsx`
- `frontend/src/test/tabularFixtures.ts`
- `docs/codex/reports/phase_21e_report.md`

## 17. Files modified

Phase 21E changes only (the much larger pre-existing working tree is preserved):

- `frontend/src/api/attachments.ts`
- `frontend/src/lib/attachmentType.ts`
- `frontend/src/components/mailbox/AttachmentAnalysisPanel.tsx`
- `frontend/src/components/mailbox/AttachmentItem.tsx`
- `frontend/src/components/mailbox/AttachmentsSection.tsx`
- `frontend/src/components/mailbox/AttachmentTypeIcon.tsx`
- `frontend/src/hooks/useAnalyzeAttachment.ts`
- `frontend/src/test/attachmentType.test.ts`
- `frontend/src/test/mailboxAttachments.test.tsx`
- `frontend/src/test/contexts.test.tsx`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md` (existing untracked file)
- `docs/roadmap/README.md` (existing modified file)

## 18. Dependency changes

None. No package manifest/lockfile changes or dependency installation. No
SheetJS, ExcelJS, spreadsheet viewer, HTML renderer, or new state library.

## 19. Tests

Focused frontend command from `frontend/`:

```sh
npm run test -- --run src/test/attachmentType.test.ts src/test/tabularAnalysis.test.tsx src/test/mailboxAttachments.test.tsx src/test/contexts.test.tsx
```

**87 passed across 4 files.** Coverage includes format gating, explicit POST,
metadata-only listing, keyboard/loading/concurrency, safe errors and retry,
all structured fields, null/empty/optional data, truncation, inert hostile text,
advisory boundaries, mixed history, generic context timeline, and axe checks.

Full `npm run test -- --run`: **369 passed across 30 files**, including mailbox,
attachment, API client, workflow, authentication, contexts, and accessibility.

Initial focused run: 64 passed, 2 failed. Both were test setup issues: an
unregistered axe matcher and a retry mock missing the backend's `detail` field.
Corrected to repository conventions before the passing runs. The initial npm
invocation from repository root found no package.json; all actual frontend
validation ran from `frontend/`.

Focused existing backend API compatibility command:

```sh
pytest -q tests/integration/test_phase21d_xlsx_analysis.py -k 'explicit_xlsx_analysis_history_and_no_side_effects or truncation_is_persisted_and_disclosed or timeline_derives_xlsx_from_owned_message_link_without_io'
```

**4 passed, 39 deselected in 2.45s.** Verifies actual Analyze/list/detail
serialization, both parser/AI truncation cases, and generic context timeline
projection using in-memory persistence, fake connectors, and mock AI. The
sandbox run timed out without output after 45 seconds; the authorized host
rerun passed. No full backend or PostgreSQL suite was rerun for these frontend
changes. No database or live provider was accessed.

## 20. Typecheck/lint/build results

Actual package scripts, run from `frontend/`:

| Check | Result |
|---|---|
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm run test -- --run` | 369 passed |
| `npm run build` | PASS — 334 modules transformed |
| `git diff --check` | PASS |

The local production build emitted a non-blocking chunk-size warning
(JavaScript bundle 667.54 kB / 185.52 kB gzip). No build was deployed.
Some shell launches emitted a non-fatal pyenv shim-write warning.

## 21. Known limitations

- XLSX only; XLS/XLSM/XLSB/CSV/TSV are unsupported.
- Intelligence is limited to the backend's bounded sample and validated AI
  observations; it is not a workbook viewer, editor, or formula evaluator.
- Backend warning strings/codes display as safe text without a new translation
  catalog. Frontend metadata recognition cannot certify content safety.
- Tests use mocked HTTP, fake connectors, and mock AI. No live provider,
  mailbox, cloud, or real-browser verification is claimed.
- The generic build's large-bundle warning remains; bundle redesign is outside
  this slice. Broader older README reconciliation is deferred to Phase 21F.

## 22. Backend changes? No

No backend production or test edits, migration creation/application, or database
changes in Phase 21E. Existing Phase 21A–21D backend work remains intact.
Alembic head remains `21d0001`.

## 23. Cloud changes? No

No Azure/AWS access, resource changes, deployments, live validation, or live AI
calls. No commit or push.

## 24. Deferred Phase 21F work

Ready for separately authorized hardening, broader offline regression,
PostgreSQL/provider-parity review, privacy/resource-bound review, and broader
documentation reconciliation. Phase 21F has not started. Overall Phase 21 is
not closed; Phase 21G live validation remains separate and requires explicit
authorization. A fresh session is recommended for the Phase 21F audit, carrying
forward this report and the preserved uncommitted Phase 21A–21E tree.

## 25. Final verdict

**PHASE 21E RESULT: PASS**
