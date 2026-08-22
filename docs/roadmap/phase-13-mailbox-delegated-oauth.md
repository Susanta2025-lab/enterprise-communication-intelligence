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
- **13B is Not Started:** credential store and refreshable access-token foundation.
- **13C is Not Started:** Google OAuth / Gmail credential lifecycle.
- **13D is Not Started:** Microsoft Entra OAuth / Graph credential lifecycle.
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

Real Google authorization URL, callback, code exchange, Gmail identity, and stored refreshable credentials.

### 13D — Microsoft Entra OAuth / Graph Credential Lifecycle

Real Microsoft authorization URL, callback, code exchange, Graph identity, and stored refreshable credentials.

### 13E — Azure Key Vault + AWS Secrets Manager Production Backends

Production secret-store implementations of the credential store. Not application-layer OAuth.

### 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression

Operational disconnect/reauthorize flows, documentation consolidation, and regression. Broad README updates belong here.

## Deliverables

- [x] Phase 13A — OAuth Domain, Authorization Session & Security Foundation (completed)
- [ ] Phase 13B — Credential Store + Refreshable Access-Token Foundation (not started)
- [ ] Phase 13C — Google OAuth / Gmail Credential Lifecycle (not started)
- [ ] Phase 13D — Microsoft Entra OAuth / Graph Credential Lifecycle (not started)
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

OAuth-created accounts in 13C/13D must always receive an explicit capability list. Known-capability execute enforcement is deferred until those accounts are connectable.

13A disconnect of an owned account sets `DISCONNECTED`, nulls `credential_ref`, and nulls `granted_capabilities`. Remaining grant metadata after the locator is removed would misrepresent the account. Provider token revocation remains 13F.

## Account status

| Status | 13A meaning |
|---|---|
| `ACTIVE` | Credential operational / account eligible subject to later capability checks |
| `DISCONNECTED` | User intentionally disconnected |
| `REAUTH_REQUIRED` | Provider credential later determined permanently unusable; user consent required again |

13A does not implement automatic transitions from token-refresh failures.
