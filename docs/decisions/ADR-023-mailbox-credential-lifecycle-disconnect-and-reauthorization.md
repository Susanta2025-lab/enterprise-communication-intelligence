# ADR-023: Mailbox Credential Lifecycle, Disconnect and Reauthorization

## Status

Accepted

Implemented in Phase 13F. This records durable mailbox credential lifecycle policy on top of ADR-021 (authorization sessions) and ADR-022 (opaque credential store). It does not replace those decisions.

## Date

Phase 13 (Production Mailbox OAuth)

## Context

Phases 13A–13E delivered delegated Gmail and Microsoft Graph OAuth, an opaque `CommunicationCredentialStore` (memory, Azure Key Vault, AWS Secrets Manager), refreshable `AccessTokenProvider` callables, and PostgreSQL advisory-lock coordination for cloud mutations. Connector accounts already had `ACTIVE`, `DISCONNECTED`, and `REAUTH_REQUIRED`, and authorization sessions already supported `purpose=REAUTHORIZE` bound to `connector_account_id`.

What remained was operational lifecycle:

- owned HTTP disconnect that actually removes ECI's delegated credential
- explicit reauthorization of an existing account without creating a second row or swapping mailboxes
- mapping confirmed permanent refresh failure onto `REAUTH_REQUIRED` without flattening that signal into Phase 12 uncertain `503`/`EXECUTING`

Three identity domains remain separate:

```text
ECI application identity:
Entra/OIDC JWT → AuthenticatedPrincipal → users.id

Mailbox delegated identity:
ECI user → Google/Microsoft consent → delegated mailbox credential

Cloud workload identity:
Azure Container Apps → Managed Identity / DefaultAzureCredential
AWS ECS → ECS Task Role / boto3 default credential chain
```

## Decision

### Local disconnect is the authoritative ECI security boundary

`POST /api/v1/connector-accounts/{id}/disconnect` requires `communications:connect`. Ownership is verified before secret-store or provider HTTP. Unknown and cross-user ids are indistinguishable `404`.

Successful local disconnect:

```text
status = DISCONNECTED
credential_ref = NULL
granted_capabilities = NULL
stored delegated credential deleted
```

Ordering:

1. Verify ownership.
2. If a locator is present, delete the credential from the store. Do not clear the database locator first.
3. Persist `DISCONNECTED` and null locator/grants.
4. If store deletion succeeds and the later database update fails, the outcome is fail-closed and retryable. ECI does not recreate the secret merely to restore availability.
5. Repeated disconnect of an already `DISCONNECTED` account is idempotent.
6. Store mutation listeners continue to invalidate cached access tokens.

After successful disconnect, ECI no longer possesses usable delegated credential material for that account. `ACTIVE` execution is rejected by the existing owned-ACTIVE gate.

### Provider revocation boundaries

Provider-side revocation is not a generic "revoke everything" mechanism.

- **Google:** a provider-scoped OAuth token revocation (`https://oauth2.googleapis.com/revoke`) may run against the refresh token belonging to this ECI authorization. Provider HTTP stays outside database transactions. Tokens are never logged. Remote revocation is **best-effort after successful local disconnect**. Remote failure must not restore locally deleted ECI access.
- **Microsoft:** ECI does **not** call Microsoft Graph `revokeSignInSessions` or any equivalent broad user-session revocation. That operation affects more than the ECI delegated application and is outside least-privilege mailbox lifecycle. There is no safe app-scoped Microsoft equivalent in this architecture. Local credential deletion is the ECI disconnect guarantee. Microsoft-side application consent may remain until the user or admin removes it through Microsoft account / Entra consent controls.

### Exact-account reauthorization

`POST /api/v1/connector-accounts/{id}/reauthorize` requires `communications:connect`. The account's stored provider is used; callers cannot switch provider or supply scopes. Server-side capability policy remains `mail.read` + `mail.send` requested; granted `mail.send` is never assumed.

Permitted states: `DISCONNECTED`, `REAUTH_REQUIRED`. `ACTIVE` returns `409` rather than silently replacing a working mailbox credential.

The session is created with `purpose=REAUTHORIZE` and `connector_account_id` equal to the owned account. Callbacks remain unauthenticated. Ownership comes exclusively from the consumed single-use session (SHA-256 state, PKCE S256).

### Mailbox identity must match

For `REAUTHORIZE`, the verified provider mailbox identity must equal the existing `ConnectorAccount.external_account_id`. Selecting a different Gmail or Microsoft mailbox at consent is rejected. The bound account is not replaced and a second connector account is not created. Newly stored secret material is compensated (deleted) on identity mismatch, provider mismatch, account-state conflict, persistence failure, or binding validation failure.

Concurrent reauthorization compare-and-set yields at most one winner. A loser compensates any newly created credential it cannot attach.

If a `REAUTH_REQUIRED` account still references old invalid credential material, that stale locator is deleted before attaching the new locator. Delete-old failure is fail-closed and retryable by starting reauthorization again. `DISCONNECTED` accounts normally have no old locator because disconnect cleared it.

### Connect-another is a distinct lifecycle

`CONNECT_ANOTHER` is not reconnect. It starts an unbound authorization session (`connector_account_id` IS NULL) and asks the provider for account selection. It does not bind or swap mailbox identity onto a different existing connector row.

Completion follows durable uniqueness `(user_id, provider, external_account_id)`:

- a new durable identity creates a new connector row
- the same **ACTIVE** identity reuses that row without mutation
- the same **DISCONNECTED** or **REAUTH_REQUIRED** identity reactivates **that** row

Reconnect remains exact-account only. `CONNECT_ANOTHER` does not weaken identity matching on `REAUTHORIZE`.

### Display identity is presentation-only

`display_identity` is an optional, nullable, human-readable mailbox label. It is never used for authorization, uniqueness, or reconnect matching. Durable provider identity remains `external_account_id` (Gmail verified Google `sub`; Microsoft verified `{tid}:{oid}`). Public connector-list, disconnect, and OAuth-callback JSON omit `external_account_id`.

### Permanent refresh failure becomes `REAUTH_REQUIRED`

`OAuthCommunicationCredentialResolver` continues to distinguish `CommunicationCredentialReauthorizationRequiredError` (confirmed `invalid_grant`) from temporary `CommunicationCredentialUnavailableError`. The resolver does not own connector-account persistence.

Gmail and Graph executors acquire an access token before provider message HTTP and preserve the reauthorization-required signal instead of flattening it into `ServiceUnavailableError`.

Because that failure is classified before provider send HTTP:

```text
mark the exact owned ConnectorAccount ACTIVE → REAUTH_REQUIRED
record the workflow action FAILED
```

The locator and last-known granted capabilities are preserved. `REAUTH_REQUIRED` is not treated like `DISCONNECTED`. Subsequent execute attempts fail the ACTIVE-account gate before TX1 and before provider I/O.

Transient store, network, or token-service unavailability retains Phase 12 semantics:

```text
workflow action remains EXECUTING
HTTP 503
account does NOT become REAUTH_REQUIRED
```

ADR-020 duplicate-send protections are unchanged. Automatic retry remains forbidden.

### PostgreSQL stores no OAuth credential material

`credential_ref` remains an opaque locator. Refresh tokens, access tokens, PKCE verifiers, authorization codes, Key Vault URIs, and Secrets Manager ARNs are not stored on `ConnectorAccount` and are not returned from application-facing APIs. PostgreSQL advisory-lock keys derive only from the opaque locator.

Expired authorization sessions remain bounded by TTL. `MailboxAuthorizationSessionService.delete_expired` exists for operator/opportunistic cleanup. Phase 13F does not add a background worker.

## Alternatives Considered

- **Clear the database locator before secret-store delete** — rejected. That can create an unrecoverable orphan while ECI still needs the locator to retry cleanup.
- **Recreate a secret after store delete / DB update failure** — rejected. Fail-closed and retryable disconnect is safer than restoring delegated access.
- **Microsoft Graph revokeSignInSessions on disconnect** — rejected. It is not app-scoped to ECI mailbox consent.
- **Allow reauthorization of ACTIVE accounts** — rejected. Silent replacement of a working grant is a credential-swap hazard.
- **Reauthorization that accepts a different mailbox identity** — rejected. That would replace mailbox A with mailbox B under the same connector-account id.
- **Flatten permanent refresh failure into HTTP 503 / EXECUTING** — rejected. Token acquisition failed before send HTTP, so the outcome is a definite no-send. Leaving `EXECUTING` would misrepresent a known non-send.
- **Have the OAuth resolver persist `REAUTH_REQUIRED`** — rejected. Relational lifecycle belongs at the application execution boundary using the exact owned account id, not a global locator lookup.

## Consequences

- Disconnect HTTP and reauthorize HTTP are production mailbox OAuth lifecycle, not a new product feature phase.
- Google remote revocation may fail without undoing local disconnect.
- Microsoft consent can outlive ECI's stored credential until removed in Microsoft/Entra controls.
- Confirmed `invalid_grant` during execute yields HTTP 200 with workflow `FAILED` and account `REAUTH_REQUIRED`, not HTTP 503.
- Phase 14E reuses the same owned `ACTIVE → REAUTH_REQUIRED` persistence on mailbox list and mailbox-backed analyze after confirmed permanent refresh failure. `credential_ref` and `granted_capabilities` are preserved. Transient refresh/store failure and mailbox HTTP 401/403 after a valid token do not mutate lifecycle.
- User-facing Gmail/Outlook → analyze HTTP is a Phase 14 capability (bounded listing and selected-message analyze). Analyze does not create a `WorkflowAction` and does not send mail. Successful Phase 14 live list→analyze left the owned connector `ACTIVE`; confirmed permanent refresh failure remains the only automatic `ACTIVE → REAUTH_REQUIRED` mutation on that path.

## Live validation

After 13F implementation, a controlled local live Gmail proof confirmed this exact-account lifecycle:

```text
ACTIVE → disconnect → DISCONNECTED
→ credential_ref and granted_capabilities cleared
→ reauthorize the same Gmail mailbox
→ same ConnectorAccount row (`eaae1e04-89a9-4c90-a2c1-f9036438de25`)
→ same external_account_id
→ ACTIVE with restored ["mail.read", "mail.send"]
```

That proof does not change the decisions above. It is not cloud-hosted ACA/ECS certification. Mailbox addresses, tokens, and secret material are not recorded here.

## Related Components

- `app/application/services/connector_accounts.py`
- `app/application/services/connector_account_oauth.py`
- `app/application/services/mailbox_oauth_reauthorization.py`
- `app/application/services/gmail_mailbox_oauth.py`
- `app/application/services/microsoft_mailbox_oauth.py`
- `app/application/services/workflow_action_execution.py`
- `app/api/routes/connector_accounts.py`
- `app/infrastructure/oauth/google.py` (`GoogleMailboxTokenRevoker`)
- [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md)
- [ADR-022](ADR-022-opaque-communication-credential-store-and-refreshable-access-tokens.md)
- [ADR-020](ADR-020-uncertain-communication-execution-semantics.md)
