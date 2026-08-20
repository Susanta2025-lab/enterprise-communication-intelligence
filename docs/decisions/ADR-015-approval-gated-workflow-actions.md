# ADR-015: Approval-Gated Workflow Actions

## Status

Accepted

The decision is implemented for Phase 11A. `WorkflowAction`, the reply-only action type, the explicit state machine, and capability-specific permission checks exist in the codebase. Persistence, HTTP workflow routes, and execution ports are not implemented.

## Date

Phase 11 (Workflow Automation)

## Context

ECI already produces AI suggestions (`DraftReply`, `ActionItem`) and fetches communications through a read-only `CommunicationConnector`. Those results are analysis output. They must not become external side effects.

Phase 8 authorization validates an OIDC JWT and then checks one configured permission (`OIDC_REQUIRED_PERMISSION`, default `communications:analyze`). That is sufficient for analyze and history. It is not sufficient for a second capability that will later propose, approve, or reject workflow actions.

Phase 10 connectors remain read-only. Write operations, if added later, must not be bolted onto the fetch port.

Future execution must follow the proven persistence pattern: short database transactions, then an external call with no open unit of work, then a short status update. Phase 11A does not persist or execute; it records that constraint so later slices do not hold a transaction across a provider call.

## Decision

Treat AI suggestions and authorized external actions as different domain concepts.

```text
AI-generated suggestion ≠ authorized external action
```

```text
Communication
    → AI analysis
    → DraftReply / ActionItem     (suggestion only)
    → explicit WorkflowAction     (proposal; not created by analyze)
    → human approval or rejection
    → later controlled execution
```

- `WorkflowAction` is the provider-independent action concept. It is not `ActionItem` and not `CommunicationAnalysisWorkflowService`.
- The only Phase 11 action type is `REPLY`.
- Status transitions are explicit and enforced in the domain. Illegal transitions raise `InvalidWorkflowTransitionError`. Terminal states in Phase 11 are `REJECTED`, `EXECUTED`, and `FAILED`.
- `DraftReply` remains suggestion output. Analyze does not create a `WorkflowAction`.
- Authentication stays JWT validation. Authorization checks a caller-supplied permission. `OIDC_REQUIRED_PERMISSION` continues to mean the analyze permission. Workflow uses `communications:workflow`. Analyze does not imply workflow, and workflow does not imply analyze.
- `CommunicationConnector` remains read-only. A future write port such as `CommunicationActionExecutor` is the intended execution boundary; it is not implemented in 11A.

## Alternatives Considered

- **Reuse `ActionItem` or add approval fields to `DraftReply`** — rejected. That would mix inference output with authorization state and make analyze a side-effecting path.
- **Extend `CommunicationConnector` with `send()` / `reply()`** — rejected. Fetch and write have different scopes, error models, and tests. Phase 10 adapters must stay read-only.
- **Replace `communications:analyze` with one global workflow permission** — rejected. History and analyze must keep their existing permission. A later real send should use a distinct `communications:send` permission, not the workflow proposal permission.
- **Implement persistence and HTTP in the same slice as the state machine** — rejected. This repository introduces contracts before tables and routes. Mixing Alembic, FastAPI, and the first permission generalization would couple unrelated failure modes.
- **A generic workflow engine (DAGs, retries, calendar/CRM/chat actions)** — rejected. Phase 11 is a governed reply action, not an automation platform.

## Consequences

- Existing analyze and history endpoints continue to require `communications:analyze`.
- Tests may mint JWTs that include `communications:workflow`. Live Entra scope provisioning is not part of 11A.
- Later persistence must own `workflow_actions` by `user_id` and keep analysis provenance. No raw message body, sender, recipients, or subject.
- Later execution must not hold a database transaction across a provider write. `FAILED` is terminal in Phase 11; retries and `EXECUTION_UNKNOWN` wait for real-provider ambiguity.
- Invalid transitions are expected to map to HTTP `409 Conflict` when workflow routes exist. That mapping is not implemented in 11A.

## Benefits

- The suggestion/action boundary is encoded, not conventional.
- Permission checks are capability-specific without breaking OIDC authentication.
- Read connectors and future write execution can evolve independently.

## Trade-offs

- `CommunicationAnalysisWorkflowService` keeps its existing name (persist-after-analyze). Contributors must distinguish it from `WorkflowAction`.
- Workflow actions are not durable or reachable over HTTP until later Phase 11 slices.
- Operators must add a live `communications:workflow` IdP scope before a production workflow API can be authorized with real tokens.

## Related Components

- `app/domain/models/workflow.py`
- `app/domain/enums.py`
- `app/domain/exceptions.py`
- `app/core/security.py`
- `app/api/dependencies.py`
- [ADR-009](ADR-009-application-user-authentication.md) (OIDC authentication; this ADR extends authorization)
- [ADR-001](ADR-001-clean-architecture.md)
- [Phase 11](../roadmap/phase-11-workflow-automation.md)
