# ADR-017: Communication Action Execution Boundary

## Status

Accepted

The decision is implemented for Phase 11D. `CommunicationActionExecutor`, the immutable `CommunicationActionExecution` command, `FakeCommunicationActionExecutor`, and `WorkflowActionExecutionService` exist in the codebase. There is no HTTP execute route and no real Gmail or Microsoft Graph write.

## Date

Phase 11 (Workflow Automation)

## Context

Phase 11A encoded `WorkflowAction` and the suggestion/action boundary. Phase 11B persisted user-owned actions with a separate approved snapshot. Phase 11C exposed create, list, get, approve, and reject over HTTP.

Approval still must not send mail. AI-generated suggestion, authorized external action, and executed external action remain distinct:

```text
AI-generated suggestion
≠
authorized external action
≠
executed external action
```

Phase 10 `CommunicationConnector` is a read/fetch port. Write side effects have different scopes, error models, and tests. Future Gmail or Graph sends must not be bolted onto that fetch contract.

Holding a database transaction across an external write would pin connections for the duration of a provider call and make failure semantics ambiguous. The persist-after-analyze path already commits identity, closes the unit of work, then calls the AI provider. Execution must follow the same short-transaction rule.

If a process crashes after a side effect succeeds but before the final status write, the stored row may remain `EXECUTING` even though the external action happened. Phase 11 accepts that uncertainty window rather than introducing retry, `EXECUTION_UNKNOWN`, outbox, or reconciliation.

## Decision

Introduce a dedicated write execution port and a two-transaction orchestration service. Keep the existing proposal/approval service and HTTP surface unchanged.

```text
APPROVED WorkflowAction
        ↓
TX1
APPROVED → EXECUTING
commit
        ↓
NO OPEN DB TRANSACTION
        ↓
CommunicationActionExecutor
        ↓
deterministic fake execution
        ↓
TX2
EXECUTING → EXECUTED
or
EXECUTING → FAILED
commit
```

- `CommunicationActionExecutor` is a domain write port separate from `CommunicationConnector`. It is synchronous. Success returns `None`. Expected execution failure raises `CommunicationActionExecutionError` with a generic public message.
- The executor receives only an immutable `CommunicationActionExecution` command: `action_id`, `action_type`, and `approved_reply_body`. The command is frozen and forbids extra fields. It does not carry the `WorkflowAction` entity, `proposed_reply_body`, `analysis_id`, owner id, provider, account, message, thread, or credentials.
- `approved_reply_body` is the authorization snapshot from the persisted `WorkflowAction`. Execution never reloads analysis, never uses `proposed_reply_body`, and never calls `AIProvider`.
- `WorkflowActionExecutionService` is a separate application service from `WorkflowActionService`. Proposal/approval lifecycle stays on `WorkflowActionService`. Execution is an irreversible side-effect orchestration concern.
- TX1 loads the owned action, calls `mark_executing()`, persists with `save_owned(expected_status=APPROVED)`, and commits. The executor is not called unless that commit succeeds.
- The unit of work is closed before `executor.execute(command)`. No database session or mutable `WorkflowAction` crosses the executor boundary.
- TX2 reloads the owned `EXECUTING` row. Fake success calls `mark_executed()` and persists with `expected_status=EXECUTING`. Known `CommunicationActionExecutionError` calls `mark_failed()` and persists the same way. Successful `FAILED` persistence is not re-raised.
- Unexpected executor exceptions are not converted into `FAILED`. Stored state may remain `EXECUTING` because the external outcome is uncertain.
- Phase 11D implements only `FakeCommunicationActionExecutor`. Failure is constructor-configured (`fail=True`). The fake records calls on the instance, performs no I/O, and does not invent provider metadata.
- There is no HTTP `execute` or `retry` route in 11D. There is no FastAPI execution-service dependency. There is no `communications:send` permission, no OAuth write scope, and no persistence schema change.

## Alternatives Considered

- **Add `send()` / `reply()` to `CommunicationConnector`** — rejected. Fetch and write have different authorization, error, and testing needs. Phase 10 adapters must stay read-only.
- **Put `execute()` on `WorkflowActionService`** — rejected. Create/get/list/approve/reject are lifecycle operations. Execution is a separate side-effecting orchestration with a mandatory transaction boundary.
- **One transaction around mark-executing, executor, and mark-executed** — rejected. A database transaction must not span the external call.
- **Call the executor, then persist EXECUTING** — rejected. `APPROVED` → `EXECUTING` must be durable before any side effect so concurrent execute attempts fail closed.
- **Use `proposed_reply_body` or regenerate a draft at execute time** — rejected. The authorized snapshot is `approved_reply_body`. Analysis deletion must not block execution.
- **Introduce `EXECUTION_UNKNOWN`, retry, outbox, or reconciliation in Phase 11** — rejected. `FAILED` remains terminal. The `EXECUTING` uncertainty window is an accepted limitation until a real provider write exists.
- **Add `POST /api/v1/workflow-actions/{id}/execute` in 11D** — rejected. 11D is an internal execution boundary. HTTP execute is later work.
- **Configure `ACTION_EXECUTOR=fake` or add an executor factory** — rejected. Phase 11D has one deterministic fake. Constructor injection is sufficient.

## Consequences

- Only `APPROVED` actions may begin execution. `PENDING`, `REJECTED`, `EXECUTING`, `EXECUTED`, and `FAILED` raise `InvalidWorkflowTransitionError` (or the existing conflict/not-found outcomes on a concurrent TX1 race) and do not call the executor.
- Unknown and cross-user actions remain `WorkflowActionNotFoundError` with zero executor calls. Identity uses `find_existing`; users are not auto-created.
- Concurrent execute attempts: one TX1 wins `APPROVED` → `EXECUTING`; the loser sees an illegal transition or `WorkflowActionConflictError`. The executor runs at most once.
- TX2 persistence failure after a fake success or known fake failure leaves the row `EXECUTING` and raises a persistence/service error.
- HTTP workflow routes, OpenAPI, and `docs/api/` are unchanged. Gmail and Graph adapters remain read-only. Alembic head remains `11b0001`.

## Benefits

- Authorized execution is an explicit port, not an implied connector write.
- The durable `EXECUTING` mark happens before any side effect.
- Proposal/approval HTTP can stay stable while execution is proven below the product surface.

## Trade-offs

- If the executor succeeds and TX2 fails, or the process crashes between them, the database may show `EXECUTING` after a completed side effect. Phase 11 does not recover that row.
- The fake does not exercise provider routing, credentials, or send permissions. Those remain later work.
- Operators cannot execute a workflow action through HTTP until a later slice adds that route.

## Related Components

- `app/domain/interfaces/communication_action_executor.py`
- `app/application/services/workflow_action_execution.py`
- `app/infrastructure/executors/fake.py`
- `app/core/exceptions.py`
- [ADR-015](ADR-015-approval-gated-workflow-actions.md)
- [ADR-016](ADR-016-workflow-persistence-and-analysis-provenance.md)
- [Phase 11](../roadmap/phase-11-workflow-automation.md)
