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

- **11A is Completed:** `WorkflowAction` domain model, `REPLY`-only action type, explicit state machine, `InvalidWorkflowTransitionError`, capability-specific permission checks (`communications:workflow`), backward-compatible `communications:analyze`.
- **11B is Completed:** `workflow_actions` persistence, user ownership, proposed-reply snapshotting, validated rehydrate, conditional expected-status updates, `WorkflowActionService` create/get/list/approve/reject, Alembic `11b0001`, ADR-016. No HTTP workflow routes or execution.
- **11C is Not started:** workflow proposal and approval API.
- **11D is Not started:** action execution port and deterministic fake executor.
- **11E is Not started:** integration, documentation closure, and regression.

Phase 11 overall is not completed.

## Deliverables

- [x] Phase 11A — Workflow Domain, State Machine & Authorization Foundation (completed)
- [x] Phase 11B — Workflow Persistence & User Ownership (completed)
- [ ] Phase 11C — Workflow Proposal and Approval API
- [ ] Phase 11D — Action Execution Port + Deterministic Fake Executor
- [ ] Phase 11E — Integration, Documentation & Regression

## Phase 11B flow

```text
owned analysis with DraftReply
        ↓
explicit WorkflowAction creation
        ↓
snapshot proposed_reply_body
        ↓
PENDING persisted action
        ↓
approve or reject
        ↓
durable state transition
```

`approve()` copies `proposed_reply_body` into `approved_reply_body`. It does not reload the analysis, accept an alternative body, or call an AI provider.

`analysis_id` is required provenance without a database FK. Analysis hard-delete leaves the workflow row, proposal, and later approval/rejection intact.

Authorization from 11A remains:

```text
authenticate JWT
    → AuthenticatedPrincipal
    → check required permission
```

- `OIDC_REQUIRED_PERMISSION` remains the analyze permission (`communications:analyze`).
- Workflow uses `communications:workflow`.
- Neither permission implies the other.

`CommunicationAnalysisService` remains AI-only. `CommunicationAnalysisWorkflowService` remains persist-after-analyze orchestration. `WorkflowActionService` is the Phase 11B application service.

## Allowed transitions

```text
PENDING   → APPROVED | REJECTED
APPROVED  → EXECUTING
EXECUTING → EXECUTED | FAILED
```

Terminal in Phase 11: `REJECTED`, `EXECUTED`, `FAILED`.

## Unavailable until later slices

- workflow REST API
- workflow execution
- Gmail send/reply
- Microsoft Graph send/reply
- production workflow automation
- automatic replies

## Deferred beyond Phase 11B

### 11C

- `/api/v1/workflow-actions` (or equivalent)
- HTTP mapping of not-found, invalid transitions, and concurrency conflicts

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
