# AGENTS.md

## Project
Enterprise Communication Intelligence (ECI)

## Working rules
- Work only inside this repository unless explicitly authorized otherwise.
- Do not commit or push unless explicitly instructed.
- Do not deploy to Azure or AWS unless explicitly instructed.
- Do not discard, reset, stash, overwrite, or remove existing uncommitted work.
- Inspect the actual repository state before making changes.
- If repository state conflicts with the task specification, stop and report the conflict.

## Architecture invariants
- Application login identity != mailbox identity != cloud workload identity != database identity != deployment identity.
- Authorization is based on verified `(iss, sub)` → internal `users.id` → application role.
- Email or mailbox identity is never an authorization key.
- Platform Owner does not bypass normal object ownership.
- AI never auto-sends communications.
- Workflow remains Analyze → Propose → Approve/Reject → Execute.
- BusinessContext ownership is server-authoritative.
- AI suggestions are advisory and must not silently mutate consequential business state.

## Attachment security
- Attachment listing must not retrieve attachment content.
- Attachment bytes may be retrieved only after explicit Analyze.
- Scanner/security validation must occur before parser or AI processing.
- Raw attachment bytes must not be durably persisted.
- Unsupported or unsafe file types fail closed.
- Do not log raw attachment contents, workbook cell values, prompts, secrets, or provider raw responses.

## XLSX / Phase 21 invariants
- Initial spreadsheet support is `.xlsx` only.
- `.xls`, `.xlsm`, `.xlsb`, `.csv`, and `.tsv` remain unsupported unless a later phase explicitly changes this.
- Use `openpyxl`.
- Never execute spreadsheet formulas.
- Never resolve external workbook links or workbook-triggered network requests.
- XLSX extraction must remain bounded.
- Reuse `attachment_analyses`; do not create a parallel XLSX persistence system without explicit architectural approval.
- AI tabular analysis remains advisory.
- Do not create Phase 22 actions, deadlines, or obligations during Phase 21.

## Development workflow
- Prefer small, phase-scoped changes.
- Do not implement later phases automatically.
- Follow existing repository conventions before introducing new abstractions.
- Reuse existing services, repositories, provider interfaces, and error models where possible.
- Avoid unnecessary dependencies.
- Do not weaken existing security controls to make a feature easier to implement.

## Validation
After relevant backend changes, run as appropriate:
- focused tests first
- full backend test suite when shared code changes
- PostgreSQL integration tests when migrations/storage change
- `ruff check .`
- `pip check`
- `git diff --check`

For frontend changes, run the repository-standard:
- typecheck
- lint
- tests
- production build

## Cloud operations
- Cloud access requires explicit authorization.
- Do not stop, delete, resize, or recreate Azure/AWS resources without explicit instruction.
- Do not broaden IAM permissions merely to work around an access failure.
- Prefer established deployment/migration runbooks.
- Live validation must verify actual cloud state before repeating a potentially completed operation.

## Completion
At the end of a phase:
- report files created and modified
- report migration changes
- report test counts/results
- report cloud resources touched
- report known limitations
- do not start the next phase unless explicitly instructed
