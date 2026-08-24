# ADR-024: Connected Mailbox Read and Analysis Authorization Boundary

## Status

Accepted

Implemented in Phase 14A. This records the public authorization and contract boundary for connected mailbox listing and mailbox-backed AI analysis. It does not replace ADR-009 (application-user OIDC), ADR-015 (`CommunicationConnector` remains read-only), ADR-017 (`CommunicationActionExecutor` remains the write port), or ADR-021/ADR-023 (mailbox OAuth lifecycle). Phase 14C mounts mailbox-backed analyze HTTP. Listing HTTP remains a later Phase 14 slice.

## Date

Phase 14 (Connected Mailbox Read and Analysis)

## Context

Phase 13 connected owned Gmail and Microsoft mailboxes through `communications:connect`. Phase 10 already implemented `CommunicationConnector` below HTTP. Direct-text analysis already exists at `POST /api/v1/communications/analyze` and is governed by `communications:analyze`.

Mailbox content retrieval and mailbox-backed AI analysis are a different product boundary from:

- mailbox OAuth lifecycle (authorize / disconnect / reauthorize)
- direct-text AI analysis
- workflow proposal / approval
- user-approved send

Collapsing those capabilities into one permission would force operators to grant more authority than a given client needs. Provider OAuth grants (`mail.read`) are also a different axis from ECI application permissions.

The public HTTP shape must stay provider-neutral. Gmail and Graph identifiers are opaque and may be long or encoding-sensitive; they must not become routing assumptions. Graph `nextLink` and other vendor pagination URLs must not appear in the public API.

## Decision

### `communications:read` is a distinct ECI permission

```text
communications:connect   authorize / disconnect / reauthorize mailbox delegation
communications:read      retrieve content from an owned connected mailbox
communications:analyze   invoke AI analysis
communications:workflow  workflow proposal / approval
communications:send      execute an external communication
```

These permissions are independent. Possessing any one does not imply another.

### HTTP authorization

Recommended future routes:

- `GET /api/v1/connector-accounts/{connector_account_id}/messages` requires `communications:read`
- `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze` requires **both** `communications:read` and `communications:analyze`

Direct-text `POST /api/v1/communications/analyze` continues to require only `communications:analyze`. It does not start requiring `communications:read`.

Mailbox operations always require an authenticated ECI principal (`AUTH_MODE=disabled` returns `401`).

Live identity-provider provisioning of the `communications:read` scope is deferred to controlled Phase 14 live validation. Phase 14A does not change live Entra configuration.

### Application authorization and provider OAuth capability remain separate

```text
ECI communications:read  !=  provider mail.read
```

Passing the ECI permission check does not mean the owned connector account is usable. Resource-level gates remain:

- connector account exists and is owned by the caller
- lifecycle status is usable for mailbox read (owned `DISCONNECTED` / `REAUTH_REQUIRED` is not)
- stored grant metadata allows read (`is_mail_read_allowed`)
- provider is supported / routable
- a usable credential locator is present

Explicit `granted_capabilities` containing `mail.read` is readable. An explicit list without `mail.read`, including `[]`, is not readable. Legacy `NULL` grants preserve existing unknown/legacy eligibility and are not treated as an explicit denial.

### Public provider message identifiers remain opaque

Mailbox-backed analyze accepts `provider_message_id` in the JSON body, not as a URL path segment. Callers treat the value as opaque transport data. Provider-specific identifier formats do not leak into routing.

### Public pagination uses an opaque provider-neutral cursor

The list contract is bounded (`page_size` with a default and an explicit maximum) and continued with `cursor` / `next_cursor`. Callers must not parse the cursor. Provider `nextLink` and other vendor pagination URLs are not part of the public response.

List items expose only provider-neutral selection metadata (`provider_message_id`, `subject`, `sender`, and normalized timestamps). They do not expose full bodies, attachments, `credential_ref`, tokens, OAuth data, raw provider JSON, or provider pagination URLs.

Mailbox-backed analyze responses reuse `CommunicationAnalysisResponse`. They do not add raw message bodies or credential material.

### `CommunicationConnector` remains the read boundary

`CommunicationConnector` stays read-only and separate from `CommunicationActionExecutor`. Phase 14 read/analyze does not send mail and does not merge read and write factories.

### Application error contract

Unknown or cross-user connector accounts remain indistinguishable `404` (`ConnectorAccountNotFoundError`). Provider messages that are not found are `404` (`MailboxMessageNotFoundError`). An owned connector account that cannot currently be used for mailbox read or mailbox-backed analyze is `409` (`ConnectedMailboxNotAvailableError`) without distinguishing DISCONNECTED, `REAUTH_REQUIRED`, missing `mail.read`, unsupported provider, or missing locator. Transient credential/provider unavailability remains `503` through existing unavailability types. Unexpected internal failures remain sanitized `500`.

## Alternatives Considered

- **Reuse `communications:connect` for mailbox content** — rejected. Connect authorizes delegation lifecycle, not reading mailbox content.
- **Reuse `communications:analyze` for mailbox listing and mailbox-backed analyze** — rejected. Analyze must not imply read, and listing must not require AI invocation authority.
- **Collapse read and analyze into one mailbox permission** — rejected. A client that lists messages should not automatically be able to invoke AI, and an analyze-only client should not retrieve mailbox content.
- **Put `provider_message_id` in the URL path** — rejected. Gmail and Graph identifiers are opaque; Graph ids may be long and encoding-sensitive.
- **Expose Graph `nextLink` or Gmail page tokens in the public API** — rejected. Pagination is an ECI-opaque cursor.
- **Treat `granted_capabilities=NULL` as an explicit denial** — rejected. Existing architecture defines `NULL` as legacy/unknown eligibility.

## Consequences

- Operators must provision `communications:read` before real-token mailbox listing or mailbox-backed analyze can succeed. That provisioning is a later live-validation step.
- Direct-text analyze clients keep working with analyze-only tokens.
- Later slices can implement listing against this contract without redesigning authorization or public schemas.
- Phase 14B implemented the provider-neutral read factory (`CommunicationConnectorFactory` / `ProviderCommunicationConnectorFactory`). Application and API code depend on that port rather than constructing Gmail or Graph connectors. Access-token acquisition stays lazy. Confirmed permanent refresh failure remains `CommunicationCredentialReauthorizationRequiredError` on the read token path. The factory does not encode ownership, ACTIVE status, or `mail.read`.
- Phase 14C mounts `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze` through `ConnectedMailboxAnalysisService`. Ownership and mailbox usability are established before credential I/O, mailbox HTTP, or AI. Bounded listing HTTP remains a later slice. Durable `ACTIVE → REAUTH_REQUIRED` mutation on confirmed refresh failure remains Phase 14E.

## Benefits

- Least privilege between connect, read, analyze, workflow, and send.
- Provider-neutral public contract that does not leak Gmail/Graph routing or pagination details.
- Resource-level mailbox usability stays separate from ECI permission checks.

## Trade-offs

- Callers that both list and analyze need two ECI permissions. That is intentional least privilege.
- Live Entra does not yet expose `communications:read`; 14A tests and local OIDC fixtures prove the application contract offline.

## Related Components

- `app/core/security.py` (`communications:read`, `authorize_all`)
- `app/api/dependencies.py` (`require_authenticated_communications_read`, `require_authenticated_communications_read_and_analyze`, `get_communication_connector_factory`)
- `app/domain/interfaces/communication_connector_factory.py`
- `app/infrastructure/connectors/factory.py` (`ProviderCommunicationConnectorFactory`)
- `app/schemas/mailbox.py`
- `app/application/exceptions.py` (`ConnectedMailboxNotAvailableError`, `MailboxMessageNotFoundError`)
- `app/domain/models/capabilities.py` (`is_mail_read_allowed`)
- [ADR-009](ADR-009-application-user-authentication.md)
- [ADR-015](ADR-015-approval-gated-workflow-actions.md)
- [ADR-017](ADR-017-communication-action-execution-boundary.md)
- [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md)
- [ADR-023](ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md)
