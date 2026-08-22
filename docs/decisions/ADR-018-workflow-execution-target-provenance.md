# ADR-018: Workflow Execution Target Provenance

## Status

Accepted

The decision is implemented for Phase 12A. Execution-target identifiers are snapshotted onto `WorkflowAction`. Analysis history stores optional `connector_account_id`. Execution still uses `FakeCommunicationActionExecutor`. There is no HTTP execute route and no real Gmail or Microsoft Graph write.

## Date

Phase 12 (Production Communication Execution)

## Context

Phase 11 made `WorkflowAction` durable and executable below HTTP through a deterministic fake. An approved action did not retain enough mailbox-routing provenance to identify the connector account and original provider message after the source analysis was deleted.

Direct-text analysis remains a valid use case and must not require a mailbox account. Existing Phase 11 workflow rows have no routing fields and must remain valid historical records. They are simply not externally executable.

Two provider concepts must stay distinct:

```text
analysis AI provider = mock / Foundry / Bedrock
communication provider = Gmail / Microsoft Graph / fake connector
```

The AI-provider persistence field must not be overloaded to represent a mailbox.

`CommunicationConnector` remains a read port. Write side effects stay on `CommunicationActionExecutor`. Credentials remain on `ConnectorAccount` only.

## Decision

Snapshot a minimal, provider-neutral execution target onto `WorkflowAction` at create time.

```text
analysis.connector_account_id → workflow_action.connector_account_id
analysis.message_id → workflow_action.provider_message_id
```

An externally executable target exists only when both identifiers are present:

```text
has_execution_target
= connector_account_id is not None
AND provider_message_id is not None
```

Half-populated combinations are rejected at domain construction and rehydration. Create persists a complete pair or both `NULL`. Legacy rows with both `NULL` remain valid and non-executable. No synthetic backfill is performed.

Mailbox-originated analyses store optional `connector_account_id` provenance. Direct-text analysis stores `NULL`. Connector ingestion supplies the id from an already owned connector-account context. Unowned ids are rejected before persistence. Analysis provenance is not execution eligibility: ingestion does not require `ACTIVE`. A later disconnect or deletion does not rewrite historical analysis provenance. Execution, not ingestion, checks owner-scoped `ACTIVE`.

`analyses.connector_account_id` and `workflow_actions.connector_account_id` are nullable provenance without database foreign keys to `connector_accounts`. Analysis-history independence is preserved. Account lifecycle remains application-managed. Execution validates the account through owner-scoped repository lookup (`get_owned`) before `APPROVED` → `EXECUTING`.

The owned `ConnectorAccount` is the source of mailbox provider identity. The execution command carries `connector_account_id`, `provider_message_id`, and `provider`. It does not carry credentials, tokens, or entire domain objects.

Execution does not reload the source analysis. Deleting the analysis after create/approve leaves the snapshotted target intact.

Phase 12A still invokes `FakeCommunicationActionExecutor` only. There is no execute-time client routing, no global `ACTION_EXECUTOR` switch, no credential resolver, and no HTTP execute route.

## Alternatives Considered

- **Reload analysis at execute time** — rejected. Analysis hard-delete would block execution, which Phase 11 already forbade.
- **Store credentials or `credential_ref` on `WorkflowAction`** — rejected. Secrets stay on `ConnectorAccount`. Phase 12B will resolve credentials.
- **Database FK from analyses/workflow_actions to connector_accounts** — rejected. That would couple analysis history and workflow durability to connector-account lifecycle.
- **Copy `external_account_id` onto `WorkflowAction`** — rejected. Mailbox identity remains on the connector account.
- **Treat half-populated targets as executable** — rejected. Both identifiers are required.
- **Backfill legacy Phase 11 rows** — rejected. Missing routing data stays `NULL` and non-executable.
- **Add `send()` / `reply()` to `CommunicationConnector`** — rejected. Read/write ports remain separate.
- **Introduce a routed executor factory or `ACTION_EXECUTOR` setting in 12A** — rejected. Provider identity comes from the owned connector account, not a global switch.

## Consequences

- Connector-ingested analyses retain `connector_account_id`. Direct-text analyses remain valid with `NULL`.
- New workflow actions snapshot routing at create. Approve, reject, and execution do not alter it.
- Targetless approved actions raise `WorkflowActionNotExecutableError` inside the execution unit of work before the `APPROVED` → `EXECUTING` write, TX1 commit, or executor call. Status remains `APPROVED`.
- Missing, cross-user, and disconnected connector accounts are the same not-executable outcome. Ownership of another user's account is not disclosed.
- Owned `ACTIVE` accounts with a complete target still execute through the fake. `ACTIVE` is structural executability in 12A; `credential_ref` is not inspected. An `ACTIVE` row may have a null locator. Credential resolution is Phase 12B.
- Alembic head is `12a0001`.

## Benefits

- Approved mailbox replies keep enough routing data after analysis deletion.
- Execution remains provider-neutral and credential-free in 12A.
- Legacy Phase 11 rows continue to list, get, and interpret terminal states.

## Trade-offs

- Direct-text workflows can be proposed and approved but cannot execute until a later product path supplies a mailbox target.
- 12A does not yet send mail, resolve credentials, or expose HTTP execute.
- Connector-account deletion or disconnect after snapshotting makes the action not executable without mutating the stored target.
- TX1 is not held open across the executor. An `ACTIVE` account may become `DISCONNECTED` after `EXECUTING` is committed; later credential/provider slices own that race.

## Related Components

- `app/domain/models/workflow.py`
- `app/domain/interfaces/communication_action_executor.py`
- `app/application/services/workflow_actions.py`
- `app/application/services/workflow_action_execution.py`
- `app/application/services/communication_ingestion.py`
- `app/application/services/analysis_history.py`
- `alembic/versions/12a0001_execution_target_provenance.py`
- [ADR-016](ADR-016-workflow-persistence-and-analysis-provenance.md)
- [ADR-017](ADR-017-communication-action-execution-boundary.md)
- [Phase 12](../roadmap/phase-12-production-communication-execution.md)
