# Phase 12 — Production Communication Execution

## Objective

Enable **user-approved real communication execution** for mailbox replies.

Phase 12 is not automatic replies. Automatic send/reply remains deferred to Phase 13+.

```text
Phase 12
= user-approved real communication execution

automatic replies
= deferred to Phase 13+
```

The Phase 11 execution model is preserved:

```text
WorkflowActionExecutionService
CommunicationActionExecution
CommunicationActionExecutor
FakeCommunicationActionExecutor
```

and the two-transaction boundary:

```text
TX1 APPROVED → EXECUTING (commit, close UoW)
executor (no DB/UoW)
TX2 EXECUTING → EXECUTED | FAILED
```

## Status

Phase 12 is **In Progress**.

- **12A is Completed:** analysis `connector_account_id` provenance, workflow execution-target snapshot (`connector_account_id` + `provider_message_id`), owned `ACTIVE` ConnectorAccount validation before `APPROVED` → `EXECUTING`, expanded frozen execution command, Alembic `12a0001`, ADR-018. Fake execution only.
- **12B is Not started:** Credential resolution and write-scope readiness.
- **12C is Not started:** Microsoft Graph reply executor.
- **12D is Not started:** Gmail reply executor.
- **12E is Not started:** Execute API and `communications:send`.
- **12F is Not started:** Failure semantics, privacy, documentation, and regression.

Phase 11 remains **Completed**.

## Planned slices

### 12A — Execution Target, Routing & Executability Foundation

Establish which mailbox account and which original provider message an approved `WorkflowAction` will later execute against.

```text
mailbox connector ingestion
        ↓
CommunicationMessage
        ↓
analysis persistence
  connector_account_id
  provider message_id
        ↓
explicit WorkflowAction creation
        ↓
snapshot execution target
  connector_account_id
  provider_message_id
        ↓
PENDING → APPROVED
        ↓
execution service validates target
        ↓
owned active ConnectorAccount
        ↓
FakeCommunicationActionExecutor
```

12A still performs **fake execution only**. It does not send mail.

### 12B — Credential Resolution + Write-Scope Readiness

Resolve mailbox credentials from the owned `ConnectorAccount`. Not implemented in this slice.

### 12C — Microsoft Graph Reply Executor

Real Graph reply writes. Not implemented in this slice.

### 12D — Gmail Reply Executor

Real Gmail reply writes. Not implemented in this slice.

### 12E — Execute API + communications:send

`POST /api/v1/workflow-actions/{id}/execute` and the send permission. Not implemented in this slice.

### 12F — Failure Semantics, Privacy, Documentation & Regression

Provider-result persistence, uncertain-outcome documentation, and Phase 12 closure. Not implemented in this slice.

## Deliverables

- [x] Phase 12A — Execution Target, Routing & Executability Foundation (completed)
- [ ] Phase 12B — Credential Resolution + Write-Scope Readiness
- [ ] Phase 12C — Microsoft Graph Reply Executor
- [ ] Phase 12D — Gmail Reply Executor
- [ ] Phase 12E — Execute API + communications:send
- [ ] Phase 12F — Failure Semantics, Privacy, Documentation & Regression

## Unavailable until later Phase 12 slices

- credential resolver / secret stores / OAuth refresh
- Gmail `messages.send` / MIME reply construction
- Microsoft Graph `/reply` / `sendMail`
- HTTP execute route
- `communications:send`
- retry, `EXECUTION_UNKNOWN`, outbox, workers
- automatic replies
