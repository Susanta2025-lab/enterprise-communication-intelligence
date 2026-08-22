# ADR-020: Uncertain Communication Execution Semantics

## Status

Accepted

The decision is implemented for Phase 12F. Production execution already follows this model: definite provider rejection becomes durable `FAILED`; confirmed success becomes durable `EXECUTED`; uncertain or unavailable outcomes after TX1 remain `EXECUTING` and the execute API returns HTTP 503. No `EXECUTION_UNKNOWN` state, outbox, automatic retry, or operator reconciliation worker is added.

## Date

Phase 12 (Production Communication Execution)

## Context

External mailbox writes are non-transactional relative to the ECI database. `WorkflowActionExecutionService` commits `APPROVED` → `EXECUTING` (TX1) and closes the unit of work before any token lookup or provider HTTP. That ordering prevents holding a database transaction across Graph `/reply` or Gmail `messages.send`.

A network failure after TX1 cannot always establish whether the provider accepted the side effect. Graph `POST /me/messages/{id}/reply` is not treated as idempotent. Gmail `users.messages.send` is not treated as idempotent. Blindly retrying either request can duplicate a reply.

Gmail performs three remote calls after the token is obtained:

```text
GET users/me/profile
→ GET users/me/messages/{id}?format=metadata
→ POST users/me/messages/send
```

Not every `ServiceUnavailableError` means an email may have been sent. Access-token secret unavailability after TX1 means the provider request did not occur. Profile or metadata timeout/5xx is pre-send unavailable: no Gmail send POST occurred. Send timeout/408/5xx/transport failure is side-effect uncertain: the message may or may not have been accepted. Graph has a single write call, so timeout/transport/408/5xx after a token was obtained is always side-effect uncertain.

Phase 12 has no reconciliation protocol, no outbox worker, and no operator tooling that can safely distinguish those cases. Introducing an explicit `EXECUTION_UNKNOWN` state without that protocol would add state-machine complexity without solving the external-side-effect ambiguity. Coercing uncertain outcomes into `FAILED` would encourage unsafe resend through a later "retry failed action" path.

## Decision

Retain the existing production model and treat `EXECUTING` after an interrupted or uncertain provider call as the durable uncertainty marker.

```text
definite provider rejection
→ CommunicationActionExecutionError
→ TX2 FAILED
→ HTTP 200 with status FAILED

confirmed provider success
→ TX2 EXECUTED
→ HTTP 200 with status EXECUTED

uncertain or unavailable outcome after TX1
→ ServiceUnavailableError
→ HTTP 503
→ stored status remains EXECUTING
```

- Definite rejection includes completed 3xx (redirects are not followed) and non-408 4xx, including Graph/Gmail 400/401/403/404/409/422/429 as applicable.
- Confirmed success is Graph HTTP 202 and Gmail profile 200 + metadata 200 + send 200. No provider result body is required. Success does not parse or persist a response payload.
- Uncertain/unavailable after TX1 includes timeout, transport failure, HTTP 408, HTTP 5xx, unexpected provider success-class status, malformed Gmail profile/metadata that cannot safely be treated as a definite send rejection, and any provider response where completion cannot be inferred.
- Access-token secret unavailability after TX1 is a separate unavailable case: a valid locator produced an executor, TX1 committed `EXECUTING`, then `AccessTokenProvider` failed. The provider request did not occur. That is not an uncertain external side effect.
- Pre-send Gmail unavailability (profile or metadata) still remains `EXECUTING` because TX1 has already committed, and no send POST occurred. Phase 12 uses one conservative operational state for pre-send unavailable, token-unavailable, and send-outcome uncertain cases.
- The execute API does not re-execute `EXECUTING`, `EXECUTED`, or `FAILED`. Those attempts return HTTP 409 with zero token calls and zero provider calls.
- Automatic retry, backoff, `Retry-After` handling, and resend are prohibited. Uncertain external side effect ≠ safe retry.
- `EXECUTION_UNKNOWN` is not implemented. No new enum value, migration, retry transition, or reconciliation route is added.
- No outbox or reconciliation worker is added. External/operator reconciliation is required before any future resend design.
- Phase 12 persists only workflow execution state. It does not persist raw Graph/Gmail responses, sent-message ids, mailbox addresses, recipients, subjects, Message-IDs, MIME, tokens, or `credential_ref`.

This decision does not claim exactly-once delivery, transactional provider execution, or idempotent send.

## Alternatives Considered

- **Add `EXECUTION_UNKNOWN` in Phase 12** — rejected. An extra state without a corresponding reconciliation/operator workflow would not make the external outcome knowable and would invite unsafe API transitions.
- **Roll uncertain outcomes back to `APPROVED`** — rejected. That would re-enable execute after a send that may already have succeeded.
- **Map timeout, transport failure, 408, or 5xx to durable `FAILED`** — rejected. `FAILED` is the definite-rejection path. Treating unknown completion as failure would encourage duplicate send.
- **Automatically retry Graph `/reply` or Gmail `messages.send`** — rejected. Neither operation is treated as idempotent. Retry can duplicate replies.
- **Parse Graph 202 or Gmail 200 bodies to persist a provider result identifier** — rejected. Graph 202 has no required body. Parsing a successful Gmail Message after the side effect could turn a completed send into an apparent local failure. No provider-neutral, safety-critical result exists to persist.
- **Add an outbox, execution-attempts table, or reconciliation worker in 12F** — rejected. Those are future work if a safe protocol is later justified. Phase 12 prioritizes duplicate-send prevention over automatic recovery.

## Consequences

- Some `workflow_actions` rows can remain `EXECUTING` indefinitely. That is deliberate fail-safe behavior.
- Operators cannot currently distinguish token unavailability, pre-send unavailability, and send-outcome uncertainty by stored status alone. All remain `EXECUTING`.
- HTTP 200 + `FAILED` means the execution request completed and a definite provider rejection was durably recorded. It is not a transport failure.
- HTTP 503 + stored `EXECUTING` means ECI cannot safely establish or complete execution. Clients must not retry automatically. For missing mailbox secret after TX1, the provider request did not occur.
- Operational tooling, attempt history, and any later safe retry strategy remain future work.
- Alembic head remains `12a0001`. No provider-result table or columns are added.

## Benefits

- Duplicate-send risk is bounded by refusing automatic retry and refusing re-execution of `EXECUTING`.
- Definite rejection stays distinguishable from unknown completion.
- The Phase 11/12 two-transaction boundary is preserved without a new state machine.
- Privacy is preserved: raw provider payloads and mailbox content are not persisted for "result" bookkeeping.

## Trade-offs

- Automatic recovery is unavailable. Stuck `EXECUTING` rows require future operator/reconciliation design.
- Pre-send Gmail failures consume the execute transition even though no send POST occurred.
- Exactly-once mailbox delivery is not provided and must not be claimed.

## Related Components

- `app/application/services/workflow_action_execution.py`
- `app/infrastructure/executors/microsoft_graph.py`
- `app/infrastructure/executors/gmail.py`
- `app/infrastructure/executors/factory.py`
- `app/api/routes/workflow_actions.py`
- [ADR-018](ADR-018-workflow-execution-target-provenance.md)
- [ADR-019](ADR-019-production-communication-write-architecture.md)
- [Phase 12](../roadmap/phase-12-production-communication-execution.md)
