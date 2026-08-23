# Phase 13 — Production Mailbox OAuth

## Objective

Replace environment-backed mailbox tokens with production delegated OAuth for Gmail and Microsoft Graph, while keeping ECI application-user OIDC separate from mailbox consent.

```text
Phase 13
= production mailbox delegated OAuth
  + credential store
  + provider credential lifecycle
  + optional cloud secret backends
  + disconnect / reauthorization hardening

automatic replies
= still deferred
```

Phase 12 execution remains the write path:

```text
APPROVED
→ TX1 EXECUTING
→ commit / close UoW
→ token/provider I/O
→ TX2 EXECUTED | FAILED
```

No OAuth or credential fields are added to `CommunicationActionExecution`.

## Status

Phase 13 is **In Progress**.

- **13A is Completed:** OAuth domain, authorization session, `communications:connect`, PKCE S256, provider-neutral capabilities, `REAUTH_REQUIRED`, schema/migration, ADR-021. No real Google or Microsoft OAuth.
- **13B is Completed:** opaque credential store, server-generated locators, in-memory store, refreshable `AccessTokenProvider` foundation, in-process cache/locks, CAS rotation, ADR-022. No real Google or Microsoft OAuth. Environment-backed execute remains the runtime default.
- **13C is Completed:** Google OAuth / Gmail credential lifecycle. Live Google Cloud project validation remains an external operator step.
- **13D is Completed:** Microsoft Entra OAuth / Graph credential lifecycle. Live Entra consent and an explicitly approved Graph reply were validated locally.
- **13E is Not Started:** Azure Key Vault + AWS Secrets Manager production backends.
- **13F is Not Started:** disconnect/reauthorization, production hardening, documentation, and regression.

Phase 12 remains **Completed**.

## Planned slices

### 13A — OAuth Domain, Authorization Session & Security Foundation

Provider-neutral security and persistence required before any live provider adapter.

- `communications:connect`
- `MailboxAuthorizationSession`
- opaque high-entropy OAuth state (hash persisted, raw state not persisted)
- PKCE S256
- `CommunicationCapability` (`mail.read`, `mail.send`)
- nullable `ConnectorAccount.granted_capabilities` with legacy `NULL` semantics
- `ConnectorAccountStatus.REAUTH_REQUIRED` storage only
- Alembic `13a0001`
- ADR-021

Out of scope: real Google/Microsoft OAuth, MSAL, google-auth, Key Vault, Secrets Manager, public authorize/callback routes, `mail.send` execute enforcement, automatic refresh-failure transitions, `credential_ref` uniqueness.

### 13B — Credential Store + Refreshable Access-Token Foundation

Server-generated locators, collision checks, and a refreshable `AccessTokenProvider` behind `credential_ref`. ADR-022 belongs here.

### 13C — Google OAuth / Gmail Credential Lifecycle

Real Google authorization URL, callback, code exchange, verified Google `sub` identity, stored refreshable credentials, explicit `granted_capabilities`, and `mail.send` execute enforcement for those explicit grants.

Implemented:

- `POST /api/v1/connector-accounts/gmail/authorize` requires `communications:connect`
- `GET /api/v1/oauth/callbacks/gmail` is unauthenticated; ownership comes from the Phase 13A session
- Confidential web-server authorization-code flow with `openid`, `gmail.readonly`, and `gmail.send`
- `access_type=offline`, PKCE S256, `prompt=consent`, `include_granted_scopes=true`
- Phase 13A raw state and PKCE challenge are used exactly; google-auth-oauthlib does not mint replacements
- State is consumed before Google token HTTP
- ID token `sub` is verified (signature, issuer, audience, expiry) and stored as `ConnectorAccount.external_account_id`
- MAIL_READ is required; MAIL_SEND is optional and must not be assumed from the request
- Refreshable material is opaque `secret_material` in the Phase 13B store (refresh token, granted scopes, subject). Access tokens and ID tokens are not stored
- Same-process development composition shares one in-memory store between callback create and refresh
- `APP_ENV=production` does not use the in-memory store as durable OAuth storage
- Gmail connector and executor remain OAuth-unaware `AccessTokenProvider` consumers

Not in 13C: live Google Cloud project setup, Microsoft OAuth, Key Vault, Secrets Manager, disconnect/reauthorize HTTP, automatic replies, or a new Alembic revision. Alembic head remains `13a0001`. Live Google consent remains an external validation step.

### 13D — Microsoft Entra OAuth / Graph credential lifecycle

Real Microsoft authorization URL, callback, code exchange, verified Graph identity, stored refreshable credentials, explicit `granted_capabilities`, and runtime token refresh through the Phase 13B resolver.

Implemented:

- `POST /api/v1/connector-accounts/microsoft_graph/authorize` requires `communications:connect`
- `GET /api/v1/oauth/callbacks/microsoft_graph` is unauthenticated; ownership comes from the Phase 13A session
- Confidential web-server Microsoft identity platform v2 authorization-code flow with `openid`, `profile`, `offline_access`, Graph `Mail.Read`, and Graph `Mail.Send`
- PKCE S256 and `prompt=consent`; Phase 13A raw state and PKCE challenge are used exactly
- State is consumed before Microsoft token HTTP
- Verified v2 ID-token `{tid}:{oid}` is stored as `ConnectorAccount.external_account_id`. `tid` is the directory tenant; `oid` is the immutable object identifier in that tenant. Email, UPN, and pairwise `sub` are not used
- MAIL_READ is required; MAIL_SEND is optional and must not be assumed from the request. Granted Graph scopes are mapped case-insensitively from the token response
- Refreshable material is opaque `secret_material` in the Phase 13B store (refresh token, granted scopes, tid, oid). Access tokens and ID tokens are not stored. MSAL is not used
- Same-process development composition shares one in-memory store between callback create and refresh; Microsoft and Gmail adapters may coexist
- `APP_ENV=production` does not use the in-memory store as durable OAuth storage
- Graph connector and executor remain OAuth-unaware `AccessTokenProvider` consumers

Not in 13D: Key Vault, Secrets Manager, disconnect/reauthorize HTTP, automatic replies, or a new Alembic revision. Alembic head remains `13a0001`. Live Entra consent and an explicitly approved Graph reply were validated outside automated CI; the controlled local analysis `connector_account_id` bind used for that smoke test is not production API behavior.

### 13E — Azure Key Vault + AWS Secrets Manager Production Backends

Production secret-store implementations of the credential store. Not application-layer OAuth.

### 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression

Operational disconnect/reauthorize flows, documentation consolidation, and regression. Broad README updates belong here.

## Deliverables

- [x] Phase 13A — OAuth Domain, Authorization Session & Security Foundation (completed)
- [x] Phase 13B — Credential Store + Refreshable Access-Token Foundation (completed)
- [x] Phase 13C — Google OAuth / Gmail Credential Lifecycle (completed)
- [x] Phase 13D — Microsoft Entra OAuth / Graph Credential Lifecycle (completed)
- [ ] Phase 13E — Azure Key Vault + AWS Secrets Manager Production Backends (not started)
- [ ] Phase 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression (not started)

## Identity boundary

```text
ECI application identity:
Entra/OIDC JWT → AuthenticatedPrincipal → users.id

Mailbox delegated authorization:
ECI user → Google/Microsoft consent → mailbox authorization credential
```

Never convert the ECI API bearer token into a mailbox credential.
Never use mailbox OAuth credentials to authenticate to the ECI REST API.

## Capability semantics

| `granted_capabilities` | Meaning |
|---|---|
| `NULL` | Legacy/environment-backed account; provider grant metadata unknown. Phase 12 execute remains eligible. |
| `[]` | Explicitly granted no mail capability. |
| `mail.read` | Known read grant. |
| `mail.read` + `mail.send` | Known read and send grant. |

OAuth-created Gmail and Microsoft Graph accounts always receive an explicit capability list. When `granted_capabilities` is explicit, execute requires `mail.send` before `APPROVED` → `EXECUTING`. Legacy environment-backed accounts with `NULL` capabilities keep Phase 12 eligibility.

13A disconnect of an owned account sets `DISCONNECTED`, nulls `credential_ref`, and nulls `granted_capabilities`. Remaining grant metadata after the locator is removed would misrepresent the account. Provider token revocation remains 13F.

## Account status

| Status | 13A meaning |
|---|---|
| `ACTIVE` | Credential operational / account eligible subject to later capability checks |
| `DISCONNECTED` | User intentionally disconnected |
| `REAUTH_REQUIRED` | Provider credential later determined permanently unusable; user consent required again |

13A does not implement automatic transitions from token-refresh failures.
