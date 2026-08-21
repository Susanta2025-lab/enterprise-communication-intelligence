# ADR-016: Workflow Persistence and Analysis Provenance

## Status

Accepted

The decision is implemented for Phase 11B. `WorkflowAction` persistence, user ownership, conditional expected-status updates, and `WorkflowActionService` exist in the codebase. HTTP workflow routes and action execution are not implemented.

## Date

Phase 11 (Workflow Automation)

## Context

Phase 11A introduced `WorkflowAction` as an approval-gated domain concept distinct from `DraftReply` and `ActionItem`. Those actions were not durable. Phase 11B must persist them as user-owned rows without turning analyze into a side-effecting path and without coupling workflow lifetime to analysis hard-delete.

A persisted proposal must remain independently meaningful if the originating analysis is later deleted. Approval must authorize a stored snapshot, not reload or regenerate content. Concurrent approve/reject must not silently overwrite a row that has already left `PENDING`.

Phase 9/10 already persist user-owned analyses and connector accounts through domain repository ports, a single `PersistenceUnitOfWork`, SQLAlchemy infrastructure, and Alembic. Workflow persistence must reuse that pattern.

## Decision

Persist `WorkflowAction` in `workflow_actions`, owned by `users.id`, with a first-class proposed-reply snapshot captured at creation.

```text
owned analysis with DraftReply
        ↓
explicit WorkflowAction creation
        ↓
snapshot proposed_reply_body
        ↓
PENDING persisted action
        ↓ approve()
approved_reply_body = proposed_reply_body
        ↓
APPROVED
```

- `proposed_reply_body` is the immutable proposal captured from `draft_reply.body` at create time.
- `approved_reply_body` is a separate authorization snapshot written on approval. Phase 11B copies the proposal; future editing may diverge. Rehydrate does not require equality.
- `analysis_id` is required opaque provenance. There is no database foreign key from `workflow_actions.analysis_id` to `analyses.id`.
- Analysis hard-delete does not remove, null, or invalidate `WorkflowAction`. A PENDING action remains approvable and rejectable after the source analysis is gone.
- Ownership is `workflow_actions.user_id` → `users.id` with `ON DELETE CASCADE`. Every query is scoped by `user_id`.
- Public construction remains `PENDING`-only. Persisted non-pending states are reconstructed through validated `WorkflowAction.rehydrate`.
- Conditional updates use `expected_status` so stale approve/reject cannot overwrite a changed row. Domain owns legal transitions; the repository owns whether the stored row is still in the expected source state.
- Raw inbound communication, sender, recipient, subject, JWT, OAuth tokens, and `credential_ref` are not stored on `workflow_actions`.

`WorkflowActionService` implements create, get, list, approve, and reject. Analyze still does not create workflow actions. HTTP routes and `CommunicationActionExecutor` remain later slices.

## Alternatives Considered

- **Foreign key from `workflow_actions.analysis_id` to `analyses.id`** — rejected. `ON DELETE CASCADE` would destroy authorized proposals. `RESTRICT` would change analysis delete semantics. `ON DELETE SET NULL` would drop required provenance. Application-managed provenance keeps analysis hard-delete unchanged.
- **Reload `DraftReply` from the analysis at approval time** — rejected. The proposal must remain independently meaningful after analysis deletion. Approval must not call an AI provider or mutate the stored proposal.
- **Accept an alternative body in `approve(approved_reply_body=...)`** — rejected for 11B. Authorization copies the already-normalized proposal. Editing is a later decision.
- **Use `model_construct` for persisted rows** — rejected. Corrupt stored lifecycle combinations must fail closed through the same domain invariants.
- **Encode the full lifecycle matrix as SQL CHECK constraints** — rejected. Bounded membership checks for `action_type` and `status` are sufficient. Domain creation and rehydrate remain authoritative.
- **A generic `workflows` table or engine** — rejected. Phase 11 persists governed reply actions only. Existing tests continue to forbid the table name `workflows`.

## Consequences

- `workflow_actions` is an application table. Alembic head is `11b0001`.
- Create requires an owned analysis with a usable `draft_reply.body`. Missing or cross-user analyses raise `AnalysisNotFoundError`. Unusable drafts raise `AnalysisHasNoDraftReplyError`.
- Unknown or cross-user actions raise `WorkflowActionNotFoundError`. Conditional update races raise `WorkflowActionConflictError`. Illegal transitions remain `InvalidWorkflowTransitionError`.
- HTTP mapping of those errors is deferred to Phase 11C. Execution remains deferred to Phase 11D.
- Operators deleting a user still cascade workflow rows through `users.id`. Operators deleting an analysis do not.

## Benefits

- Authorized reply snapshots survive analysis history deletion.
- Ownership isolation matches analyses and connector accounts.
- Concurrent state changes fail closed instead of last-write-wins.

## Trade-offs

- Orphan `analysis_id` values are possible and expected after analysis hard-delete.
- `approved_reply_body` duplicates `proposed_reply_body` in Phase 11B. The separate column exists so later editing can change the authorized snapshot without rewriting history.
- Workflow actions are not reachable over HTTP until Phase 11C.

## Related Components

- `app/domain/models/workflow.py`
- `app/domain/interfaces/workflow_action_repository.py`
- `app/application/services/workflow_actions.py`
- `app/infrastructure/storage/models.py`
- `app/infrastructure/storage/repositories/workflow_action.py`
- `alembic/versions/11b0001_workflow_actions.py`
- [ADR-012](ADR-012-postgresql-persistence-architecture.md)
- [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-015](ADR-015-approval-gated-workflow-actions.md)
- [Phase 11](../roadmap/phase-11-workflow-automation.md)
