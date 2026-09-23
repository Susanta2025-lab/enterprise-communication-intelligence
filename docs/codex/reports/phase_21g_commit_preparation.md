# Phase 21G — Commit preparation (2026-09-23)

## Proposed commit

```text
feat: add XLSX tabular intelligence and close Phase 21
```

This proposal covers the complete preserved Phase 21 implementation, tests,
existing migration, packaging changes and documentation. The implementation was
already present on entry to this documentation-only pass; no application code,
tests, dependency or migration files were changed here. Branch `master`, baseline
HEAD `63669ec8bdf27158817e4fe56858fd3df3ce3086`. Nothing is staged, committed or
pushed. Separate user approval is required before committing or pushing.

## Closure assessment

Phase 21G PASS; Phase 21 CLOSED for the delivered XLSX scope, based on accepted
local Phase 21A–F evidence and the operator's manual Azure/AWS completion report.
The failed Azure frontend upload and all other original Phase 21G checkpoints
are preserved verbatim; successful completion is appended. See
[the final report](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations)
for evidence provenance and limitations. Logs alone do not prove parsing could
not start before CLEAN; source/integration tests support that stronger guarantee.
No exhaustive live security, performance or accessibility certification is claimed.
No Phase 22 work is authorized or started.

## Changes made in this documentation pass

Modified documentation:

- `README.md`
- `deployment/aws/README.md`
- `deployment/azure/README.md`
- `docs/api/README.md`
- `docs/cloud/roadmap.md`
- `docs/codex/reports/phase_21a_report.md`
- `docs/codex/reports/phase_21b_report.md`
- `docs/codex/reports/phase_21c_report.md`
- `docs/codex/reports/phase_21d_report.md`
- `docs/codex/reports/phase_21e_report.md`
- `docs/codex/reports/phase_21g_report.md`
- `docs/roadmap/README.md`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`

Created this commit preparation report. Phase 21A–E edits only update their
historical-slice status banners to link to final closure. Added narrow root
`.gitignore` rules for `/.phase21*.xml` and `/.phase21g-artifacts/`; existing
environment/backup ignore rules remain in place. No local files were removed.

## Repository review and checks

- Reviewed status, tracked diff scope, existing Phase 21 reports, migration,
  scanner/analysis/persistence flow and relevant integration test assertions.
  This is commit-scope and documentation consistency review, not a fresh full
  implementation/security audit.
- File fingerprints confirmed all pre-existing non-documentation changes were
  preserved; all original Phase 21G report content remains intact.
- `git diff --check`: PASS. Additional candidate-file whitespace and merge-marker
  checks cover untracked files too.
- Local Markdown target checks: PASS after creation of this report.
- Static migration graph inspection: one head `21d0001`, parent `20c0001`.
  No database connection or migration execution. No new migration added here.
- Candidate-file secret-pattern scan: no matches for private keys, AWS access
  keys, JWTs, GitHub tokens, credential-bearing URLs or literal secret assignments.
  Candidate path review excludes credentials, temporary XML, generated deployment
  files and backups. This bounded scan is not a universal secret-detection proof.
- `git check-ignore`: PASS for all four temporary Phase 21 XML files,
  `.phase21g-artifacts/`, `.env` and sample `.bak`/`.tmp` paths.
- No application tests, builds or dependency checks rerun for documentation-only
  changes. Historical accepted results: 2,681 backend tests (including 94
  PostgreSQL), 369 frontend tests across 30 files, and 86 Phase 21G focused tests.
- Cloud resources accessed or modified in this pass: **none**. No deployment,
  migration, AI invocation, attachment retrieval or XLSX analysis performed.

## AGENTS.md decision and exclusions

`AGENTS.md` was read separately and matches the supplied repository instructions.
It contains repository-wide agent policy and is not required to ship the XLSX
feature. Proposed decision: **exclude from this commit**, retain it untracked
and unchanged, and leave its versioning to a separate policy decision. Do not
use `git add .` or `git add -A`; any later staging must use the explicit inventory.

Excluded, retained locally:

- `AGENTS.md`
- `.phase21d-full.xml`, `.phase21d-full-final.xml`
- `.phase21f-full.xml`, `.phase21f-full-final.xml`
- `.phase21g-artifacts/` in its entirety, including generated deployment files
- Ignored environment/credential files, logs, build outputs and local backups

No secrets or temporary artifacts are included in the proposed inventory.
Sanitized artifact hashes and resource names in reports are release evidence,
not credentials. No staging is performed by this report.

## Exact files proposed for staging

84 files, including this report. This is an explicit reviewed proposal, not
an instruction to include future working-tree changes automatically.

- `.dockerignore`
- `.gitignore`
- `README.md`
- `alembic/versions/21d0001_attachment_analyses_kind_xlsx.py`
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
- `app/domain/models/tabular_analysis.py`
- `app/domain/models/workbook_extraction.py`
- `app/domain/schemas/__init__.py`
- `app/domain/schemas/tabular_analysis.py`
- `app/infrastructure/attachments/parser.py`
- `app/infrastructure/attachments/xlsx.py`
- `app/infrastructure/storage/models.py`
- `app/infrastructure/storage/repositories/attachment_analysis.py`
- `app/providers/amazon_bedrock/output.py`
- `app/providers/amazon_bedrock/provider.py`
- `app/providers/common/prompts.py`
- `app/providers/common/tabular_input.py`
- `app/providers/common/tabular_output.py`
- `app/providers/common/tabular_prompts.py`
- `app/providers/microsoft_foundry/output.py`
- `app/providers/microsoft_foundry/provider.py`
- `app/providers/mock/provider.py`
- `app/schemas/attachments.py`
- `deployment/aws/README.md`
- `deployment/azure/README.md`
- `docs/api/README.md`
- `docs/api/endpoints.md`
- `docs/api/request-response-models.md`
- `docs/cloud/roadmap.md`
- `docs/codex/reports/phase_21_readiness_assessment.md`
- `docs/codex/reports/phase_21a_report.md`
- `docs/codex/reports/phase_21b_report.md`
- `docs/codex/reports/phase_21c_report.md`
- `docs/codex/reports/phase_21d_report.md`
- `docs/codex/reports/phase_21e_report.md`
- `docs/codex/reports/phase_21f_report.md`
- `docs/codex/reports/phase_21g_commit_preparation.md`
- `docs/codex/reports/phase_21g_report.md`
- `docs/roadmap/README.md`
- `docs/roadmap/phase-21-xlsx-tabular-intelligence.md`
- `frontend/src/api/attachments.ts`
- `frontend/src/components/mailbox/AttachmentAnalysisPanel.tsx`
- `frontend/src/components/mailbox/AttachmentItem.tsx`
- `frontend/src/components/mailbox/AttachmentTypeIcon.tsx`
- `frontend/src/components/mailbox/AttachmentsSection.tsx`
- `frontend/src/components/mailbox/TabularAnalysisPanel.tsx`
- `frontend/src/hooks/useAnalyzeAttachment.ts`
- `frontend/src/lib/attachmentType.ts`
- `frontend/src/test/attachmentType.test.ts`
- `frontend/src/test/contexts.test.tsx`
- `frontend/src/test/mailboxAttachments.test.tsx`
- `frontend/src/test/tabularAnalysis.test.tsx`
- `frontend/src/test/tabularFixtures.ts`
- `pyproject.toml`
- `tests/integration/test_phase21d_xlsx_analysis.py`
- `tests/postgres/test_phase21d_xlsx.py`
- `tests/postgres/test_phase21f_atomicity.py`
- `tests/support/in_memory_persistence.py`
- `tests/unit/application/test_attachment_analysis.py`
- `tests/unit/domain/test_attachment_policy.py`
- `tests/unit/domain/test_enums.py`
- `tests/unit/domain/test_phase21a_xlsx_security.py`
- `tests/unit/domain/test_phase21f_xlsx_hardening.py`
- `tests/unit/infrastructure/attachments/fixtures.py`
- `tests/unit/infrastructure/attachments/test_parser_dispatcher.py`
- `tests/unit/infrastructure/attachments/test_xlsx_parser.py`
- `tests/unit/infrastructure/storage/test_alembic.py`
- `tests/unit/infrastructure/storage/test_attachment_analysis_repository.py`
- `tests/unit/infrastructure/storage/test_models.py`
- `tests/unit/infrastructure/storage/test_phase21d_migration.py`
- `tests/unit/providers/test_tabular_analysis_parity.py`
- `tests/unit/providers/test_tabular_input.py`
- `tests/unit/providers/test_tabular_output.py`
- `tests/unit/providers/test_tabular_prompts.py`
