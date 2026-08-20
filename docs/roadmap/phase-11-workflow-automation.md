# Phase 11 — Workflow Automation

## Objective

Introduce an approval-gated workflow-action layer so AI suggestions cannot become external side effects.

```text
AI-generated suggestion ≠ authorized external action
```

Phase 11 is a governed `REPLY` action derived from an existing analysis. It is not a generic workflow engine.

## Business Value

- Makes the suggestion/action boundary explicit in the domain.
- Requires a human decision before any later execution.
- Generalizes authorization so analyze and workflow are independent capabilities.
- Keeps `CommunicationConnector` read-only and `AIProvider` unchanged.

## Status

Phase 11 is **In progress**.

- **11A is Completed:** `WorkflowAction` domain model, `REPLY`-only action type, explicit state machine, `InvalidWorkflowTransitionError`, capability-specific permission checks (`communications:workflow`), backward-compatible `communications:analyze`. No persistence, HTTP workflow routes, or execution.
- **11B is Not started:** workflow persistence and user ownership.
- **11C is Not started:** workflow proposal and approval API.
- **11D is Not started:** action execution port and deterministic fake executor.
- **11E is Not started:** integration, documentation closure, and regression.

Phase 11 overall is not completed.

## Deliverables

- [x] Phase 11A — Workflow Domain, State Machine & Authorization Foundation (completed)
- [ ] Phase 11B — Workflow Persistence & User Ownership
- [ ] Phase 11C — Workflow Proposal and Approval API
- [ ] Phase 11D — Action Execution Port + Deterministic Fake Executor
- [ ] Phase 11E — Integration, Documentation & Regression

## Phase 11A Architecture

```text
Communication
    ↓
AI analysis
    ↓
DraftReply / ActionItem          (suggestion only)
    ↓
explicit WorkflowAction          (PENDING; not created by analyze)
    ↓
approve / reject                 (domain state machine)
    ↓
later: EXECUTING → EXECUTED | FAILED
```

Authorization:

```text
authenticate JWT
    → AuthenticatedPrincipal
    → check required permission
```

- `OIDC_REQUIRED_PERMISSION` remains the analyze permission (`communications:analyze`).
- Workflow uses `communications:workflow`.
- Neither permission implies the other.

`CommunicationAnalysisService` remains AI-only. `CommunicationAnalysisWorkflowService` remains persist-after-analyze orchestration. It is not the Phase 11 workflow service.

## Allowed transitions

```text
PENDING   → APPROVED | REJECTED
APPROVED  → EXECUTING
EXECUTING → EXECUTED | FAILED
```

Terminal in Phase 11: `REJECTED`, `EXECUTED`, `FAILED`.

## Unavailable in 11A (and still unavailable until later slices)

- workflow persistence
- workflow REST API
- workflow execution
- Gmail send/reply
- Microsoft Graph send/reply
- production workflow automation
- automatic replies

## Deferred beyond Phase 11A

### 11B

- `workflow_actions` table, Alembic migration, repository, Unit of Work property
- user-owned persistence and create-from-owned-analysis

### 11C

- `/api/v1/workflow-actions` (or equivalent)
- HTTP mapping of invalid transitions to `409`

### 11D

- `CommunicationActionExecutor` and `FakeCommunicationActionExecutor`
- execute-after-approval with no database transaction across the executor call

### 11E

- Phase 11 closure documentation and full regression
- no new product capability

### Later connector-write / productionization

- Gmail send/reply, Microsoft Graph sendMail/reply
- `communications:send`
- production mailbox OAuth, credential resolver, secret stores
- connector HTTP APIs, mailbox onboarding
- retries, `EXECUTION_UNKNOWN`, automatic replies
- calendar, CRM, Slack, or Teams workflow types
