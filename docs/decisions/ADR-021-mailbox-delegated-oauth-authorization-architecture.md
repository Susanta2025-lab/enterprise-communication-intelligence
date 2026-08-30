# ADR-021: Mailbox Delegated OAuth Authorization Architecture

## Status

Accepted

The decision is implemented for Phase 13A. The provider-neutral authorization-session, capability, permission, and persistence foundation exists. Real Google OAuth, Microsoft OAuth, refresh, Key Vault, and Secrets Manager were delivered in 13C–13E. Disconnect, reauthorization, and permanent-refresh lifecycle policy are recorded in [ADR-023](ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md).

## Date

Phase 13 (Production Mailbox OAuth)

## Context

Phase 12 executes user-approved mailbox replies using environment-backed `credential_ref` locators. That is not production delegated OAuth. Production mailbox access requires a user of ECI to grant Google or Microsoft consent for a mailbox, independently of the ECI application-user OIDC login.

Those identity paths must not be mixed:

```text
ECI application identity:
Entra/OIDC JWT → AuthenticatedPrincipal → users.id

Mailbox delegated authorization:
ECI user → Google/Microsoft consent → mailbox authorization credential
```

The ECI API bearer token must never become a mailbox credential. Mailbox OAuth credentials must never authenticate to the ECI REST API.

Phase 12 environment-backed development accounts may reuse an opaque `credential_ref` such as `demo-account`. A database-wide unique constraint on `credential_ref` would break that path. Future OAuth locators will be server-generated high-entropy values checked for collision by a credential store, not by a unique index introduced in 13A.

## Decision

Mailbox OAuth is a server-side authorization transaction, not a client-driven token hand-off.

```text
authenticated ECI user (communications:connect)
→ start mailbox authorization session
→ persist SHA-256(state), PKCE verifier, requested capabilities
→ later unauthenticated callback supplies raw state
→ consume session (single-use)
→ future provider code exchange (13C/13D)
```

Durable rules:

- Mailbox OAuth is separate from ECI application-user OIDC.
- The authorization transaction is server-side. Public 13A HTTP does not expose authorize or callback routes; those wait for real provider adapters in 13C/13D.
- The session is PostgreSQL-backed and short-lived (default 10 minutes; bounded 60–1800 seconds).
- OAuth `state` is opaque high-entropy material (`secrets.token_urlsafe(32)`, ≥256 bits).
- Raw state is never persisted. SHA-256(hex) is persisted and is unique.
- State is single-use. Consume is a conditional `UPDATE ... RETURNING` compare-and-set: matching `state_hash`, provider, `consumed_at IS NULL`, and `expires_at > now`. Concurrent consume yields at most one success. The losing statement does not receive the PKCE verifier.
- The session is bound to the internal ECI `user_id` and mailbox provider (`gmail` or `microsoft_graph`).
- Session purpose is one of:
  - `connect` — unbound. `connector_account_id` **must be NULL**. First mailbox connection.
  - `connect_another` — unbound. `connector_account_id` **must be NULL**. Distinct account-selection flow. It must not bind or repurpose a different existing connector row.
  - `reauthorize` — bound to an owned `connector_account_id`. Exact-account only; see [ADR-023](ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md).
- The provider callback does not require or expect an ECI bearer token. Ownership comes from the session.
- PKCE method is S256 only. `plain` is not supported.
- Clients do not control the redirect target, requested capabilities, or `credential_ref`.
- Tokens are never returned from a callback and are never stored on the authorization session.
- Provider endpoint URLs are not configurable by clients.
- `communications:connect` is a distinct permission from analyze, workflow, and send.
- Future provider adapters belong in infrastructure.
- Future mailbox credentials stay behind the `credential_ref` / credential-store abstraction.
- `credential_ref` database uniqueness is deliberately **not** introduced in 13A. Future OAuth locators are generated server-side. Future HTTP OAuth APIs must never accept a client-supplied `credential_ref`.
- Disconnect in 13A sets `DISCONNECTED`, nulls `credential_ref`, and nulls `granted_capabilities`. It does not revoke provider tokens.

`ConnectorAccount.granted_capabilities` is provider-neutral (`mail.read`, `mail.send`). `NULL` means a legacy/environment-backed account whose provider grant metadata is unknown. An explicit empty list means no mail capability. Phase 13A does not require `mail.send` for Phase 12 execute eligibility.

`ConnectorAccountStatus.REAUTH_REQUIRED` is stored for later credential-lifecycle work. 13A does not automatically transition accounts from token-refresh failures.

## Alternatives Considered

- **Convert the ECI JWT into a mailbox credential** — rejected. That would mix application identity with delegated mailbox consent.
- **Persist raw OAuth state** — rejected. The raw value is a CSRF secret and must exist only with the redirect.
- **Client-supplied scopes, redirect URIs, or credential_ref** — rejected. Those create open-redirect, privilege-escalation, and secret-locator injection surfaces.
- **Unique index on credential_ref in 13A** — rejected. Phase 12 environment-backed accounts may reuse locators such as `demo-account`.
- **Public authorize/callback routes in 13A** — rejected. There is no real provider code exchange yet. Incomplete OAuth HTTP would not be a production contract.
- **Add MSAL / google-auth in 13A** — rejected. Provider SDKs belong with 13C/13D adapters.

## Consequences

- 13C/13D can complete code exchange after consume closes the unit of work, using the in-memory PKCE verifier.
- Environment-backed Phase 12 execute remains valid for `granted_capabilities=NULL`.
- Operators must provision `communications:connect` before a future connect API can authorize with real tokens.
- A later `CommunicationCredentialStore` must reject locator collisions when creating stored credentials.

## Benefits

- The mailbox consent transaction is explicit, short-lived, and single-use.
- Identity classes stay separated.
- Phase 12 development accounts keep working.

## Trade-offs

- PKCE verifiers are stored briefly in PostgreSQL during 13A. They are never logged, never exposed through API, cleared on consume, and TTL-bounded. A later secret-store-backed verifier is not required for this slice.
- Public OAuth HTTP is deferred, so 13A cannot be live-certified against Google or Microsoft.

## Related Components

- `app/application/services/mailbox_authorization_sessions.py`
- `app/domain/interfaces/mailbox_authorization_session_repository.py`
- `app/core/pkce.py`
- `app/core/oauth_state.py`
- `app/core/security.py` (`communications:connect`)
- [ADR-009](ADR-009-application-user-authentication.md)
- [ADR-019](ADR-019-production-communication-write-architecture.md)
