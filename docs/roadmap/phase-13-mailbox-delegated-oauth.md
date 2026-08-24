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

Phase 13 is **Completed**.

- **13A is Completed:** OAuth domain, authorization session, `communications:connect`, PKCE S256, provider-neutral capabilities, `REAUTH_REQUIRED`, schema/migration, ADR-021. That slice did not implement real Google or Microsoft OAuth.
- **13B is Completed:** opaque credential store, server-generated locators, in-memory store, refreshable `AccessTokenProvider` foundation, in-process cache/locks, CAS rotation, ADR-022. That slice did not implement real Google or Microsoft OAuth. Environment-backed execute remains the local/dev default for legacy locators.
- **13C is Completed:** Google OAuth / Gmail credential lifecycle. Live Google consent and an explicitly approved Gmail reply were validated locally. That is not cloud-hosted ACA/ECS OAuth certification.
- **13D is Completed:** Microsoft Entra OAuth / Graph credential lifecycle. Live Entra consent and an explicitly approved Graph reply were validated locally. That is not cloud-hosted ACA/ECS OAuth certification.
- **13E is Completed:** Azure Key Vault and AWS Secrets Manager `CommunicationCredentialStore` backends, explicit `CREDENTIAL_STORE_BACKEND` selection, production fail-closed rules, PostgreSQL advisory-lock coordination, and live Azure/AWS store validation recorded below.
- **13F is Completed:** owned disconnect HTTP, exact-account reauthorization, Google best-effort token revocation, Microsoft local-only disconnect, permanent refresh → `REAUTH_REQUIRED`, production hardening, documentation consolidation, and regression. No new live Google/Microsoft/Azure/AWS calls were made in 13F.

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

Not in 13C: Microsoft OAuth, Key Vault, Secrets Manager, disconnect/reauthorize HTTP, automatic replies, or a new Alembic revision. Alembic head remains `13a0001`. Live Google consent and an explicitly approved Gmail reply were validated locally outside automated CI; that is not cloud-hosted ACA/ECS OAuth certification. The controlled local analysis `connector_account_id` bind used for that smoke test is not production API behavior.

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

Durable `CommunicationCredentialStore` implementations. Not application-layer OAuth.

Implemented:

- `CREDENTIAL_STORE_BACKEND=memory | azure_key_vault | aws_secrets_manager`
- Azure Key Vault store using `DefaultAzureCredential` (Container Apps managed identity). Configuration holds only `AZURE_KEY_VAULT_URL`.
- AWS Secrets Manager store using the default boto3 chain (ECS task role). Configuration holds region and `eci/mailbox-oauth` namespace. No AWS access keys in Settings.
- Locator `oauth-{hex}` maps to Key Vault secret `eci-oauth-{hex}` and Secrets Manager id `eci/mailbox-oauth/oauth-{hex}`. `ConnectorAccount` still stores only the opaque locator.
- Compare-and-set uses a logical version in a minimal envelope. Azure Key Vault does not provide a linearizable CAS primitive. Credential cloud mutations use PostgreSQL transaction-scoped advisory locks (`pg_advisory_xact_lock`) keyed deterministically by the opaque `credential_ref`. PostgreSQL stores coordination only; no OAuth secret or token material. Same-locator create / replace / delete serialize across ECI instances that share the same PostgreSQL database. AWS retains native `AWSPENDING` / `AWSCURRENT` version-stage compare-and-set in addition to PostgreSQL serialization. Credential mutation transactions hold one database connection during the infrequent cloud control-plane write.
- Production rejects `memory` and rejects mailbox OAuth unless a complete Azure or AWS backend is configured. `AI_PROVIDER` does not select the mailbox store.
- Gmail and Microsoft Graph adapters remain store-unaware.
- AWS `get()` treats a secret scheduled for deletion (`DeletedDate`) as absent. `InvalidRequestException` is not broadly mapped to None; `DescribeSecret` confirms that state. Idempotent `delete()` of an already-scheduled secret is a no-op after the same check.
- AWS IAM on `eci/mailbox-oauth/*`: `secretsmanager:CreateSecret`, `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, `DescribeSecret`, `DeleteSecret`. Do not grant `ListSecrets` or `SecretsManagerFullAccess`.

Not in 13E: disconnect HTTP, automatic replies, Terraform/Bicep, a new Alembic revision, or cloud-hosted Gmail/Graph OAuth certification. Live Key Vault and Secrets Manager store validation is recorded below.

PostgreSQL validation (with `ECI_POSTGRES_TEST_DATABASE_URL` enabled):

- `tests/postgres/test_credential_mutation_coordination.py`: 4 passed
- complete `tests/postgres` suite: 70 passed
- complete suite: 1720 passed, 0 skipped

Azure live validation used the existing development Key Vault `eci-kv-oauth-dev-susanta` (Spain Central, RBAC authorization enabled). The path was factory → PostgreSQL advisory coordinator → `AzureKeyVaultCommunicationCredentialStore` → `DefaultAzureCredential` → Azure Key Vault.

Live evidence:

- create passed
- get passed
- normal version replacement passed
- stale-version rejection passed
- two independently constructed stores raced with the same expected version: exactly one winner and one loser
- winning material remained persisted
- coordinated delete passed
- synthetic probe secret was removed

This does not claim that Azure Key Vault itself supplies atomic CAS.

AWS live validation used the existing ECI developer identity (profile/session) in `eu-south-2`. The path was factory → PostgreSQL advisory coordinator → `AwsSecretsManagerCommunicationCredentialStore` → boto3/default AWS authentication → AWS Secrets Manager.

Live evidence:

- create passed
- get passed
- normal version replacement passed
- two independently constructed stores raced with the same expected version: exactly one winner and one loser
- winning material remained persisted
- delete succeeded using the existing 7-day recovery window
- scheduled-for-deletion `GetSecretValue` behavior was corrected and live validated to map to provider-neutral absence (`None`) after confirming `DeletedDate` with `DescribeSecret`

Required least-privilege AWS actions remain `CreateSecret`, `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, `DeleteSecret`, and `DescribeSecret`. `secretsmanager:ListSecrets` is not required. `SecretsManagerFullAccess` is not recommended.

Final code verification for this slice: `python -m pip check` passed; `python -m ruff check .` passed; full pytest with PostgreSQL integration enabled: 1720 passed.

### 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression

Operational mailbox credential lifecycle on the Phase 13A–13E foundation. No Alembic revision. ADR-023 records the durable decisions. Broad README and architecture documentation consolidation belongs here.

Implemented:

**Disconnect**

- `POST /api/v1/connector-accounts/{connector_account_id}/disconnect` requires `communications:connect`
- Ownership is verified before secret-store or provider HTTP. Unknown and cross-user ids are indistinguishable `404`
- Response is sanitized connector-account metadata only (`id`, `provider`, `external_account_id`, `status`, granted capabilities, timestamps). Never `credential_ref`, tokens, or store URIs
- Successful local disconnect: `status=DISCONNECTED`, `credential_ref=NULL`, `granted_capabilities=NULL`, stored delegated credential deleted
- Store delete happens before clearing the database locator. Store unavailability while deletion is required fails closed (`503`) and leaves the locator
- Store delete success plus later DB update failure remains fail-closed and retryable; the secret is not recreated
- Repeated disconnect of an already `DISCONNECTED` account is idempotent
- Cached access tokens are invalidated by existing store mutation listeners
- Local credential deletion is the authoritative ECI security boundary: after success ECI no longer possesses usable delegated material for that account

**Provider revocation**

- Google: `GoogleMailboxTokenRevoker` posts the refresh token to `https://oauth2.googleapis.com/revoke` best-effort after successful local disconnect. Remote failure does not restore local access. Tokens are never logged. Provider HTTP stays outside database transactions
- Microsoft: no Graph `revokeSignInSessions` or other broad session revocation. Local credential deletion is the ECI guarantee. Microsoft-side application consent may remain until the user or admin removes it through Microsoft/Entra consent controls

**Reauthorization**

- `POST /api/v1/connector-accounts/{connector_account_id}/reauthorize` requires `communications:connect`
- Uses the bound account's provider. Callers cannot switch provider or supply scopes
- `DISCONNECTED` and `REAUTH_REQUIRED` are accepted. `ACTIVE` returns `409`
- Starts `MailboxAuthorizationSession` with `purpose=REAUTHORIZE` and the exact owned `connector_account_id`
- PKCE S256 and high-entropy single-use SHA-256 state remain as in 13A. Callback remains unauthenticated
- Callback requires `purpose=REAUTHORIZE` and a bound account id. Verified provider mailbox identity must equal the existing `external_account_id`. Selecting a different mailbox is rejected; a second connector account is not created
- Successful reauthorization reactivates the exact bound account: `ACTIVE`, new opaque `credential_ref`, freshly granted capability list
- Newly created secret material is compensated on identity/provider mismatch, account-state conflict, persistence failure, or binding validation failure
- Concurrent reauthorization compare-and-set yields at most one winner; a loser deletes any newly created credential it cannot attach
- Stale `REAUTH_REQUIRED` locators are deleted before attaching the new locator. Delete-old failure is fail-closed and retryable by starting reauthorization again

**Permanent refresh → `REAUTH_REQUIRED`**

- Confirmed `CommunicationCredentialReauthorizationRequiredError` (for example `invalid_grant`) during execute marks the exact owned account `ACTIVE` → `REAUTH_REQUIRED`
- Locator and last-known granted capabilities are preserved. Subsequent execute fails the ACTIVE gate before TX1 and before provider I/O
- Token acquisition happens before provider send HTTP, so a confirmed permanent refresh failure records workflow `FAILED` (definite no-send) rather than leaving `EXECUTING`
- Transient store/network/token-service unavailability keeps Phase 12 semantics: action remains `EXECUTING`, HTTP `503`, account does **not** become `REAUTH_REQUIRED`
- ADR-020 duplicate-send protections are unchanged. Gmail and Graph executors remain OAuth-unaware `AccessTokenProvider` consumers except for preserving the dedicated reauthorization-required signal

**Production hardening**

- OAuth state remains SHA-256 only in PostgreSQL. PKCE verifier never leaves server persistence
- Production still rejects the in-memory credential backend. Azure uses `DefaultAzureCredential`; AWS uses the boto3 default chain. No AWS access-key or Azure client-secret Settings
- PostgreSQL advisory-lock keys derive only from opaque `credential_ref`. PostgreSQL stores no OAuth credential material
- Expired authorization sessions remain TTL-bounded. `MailboxAuthorizationSessionService.delete_expired` exists for operator/opportunistic cleanup. Phase 13F does not add a background worker
- Automatic replies, mailbox synchronization/webhooks, retry/reconciliation/exactly-once delivery, and user-facing connector ingestion HTTP remain out of scope

Not in 13F: a new Alembic revision, managed Azure PostgreSQL / Amazon RDS, cloud-hosted Gmail/Graph OAuth certification of the retained ACA/ECS services, live disconnect/reauthorize against real Google or Microsoft mailboxes, or any new cloud resource. 13F automated implementation used fakes/mocks only.

Automated verification:

- `python -m pip check` passed
- `python -m ruff check .` passed
- targeted 13F and related regression tests: 760 passed
- `tests/postgres` with `ECI_POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://eci:eci@localhost:5433/eci_test`: 71 passed
- full pytest with PostgreSQL enabled: 1753 passed
- `git diff --check` passed

No live Google, Microsoft, Azure, or AWS calls were made in 13F. Cached cloud/OAuth credentials were not consumed. No cloud resources were created or deleted.

## Deliverables

- [x] Phase 13A — OAuth Domain, Authorization Session & Security Foundation (completed)
- [x] Phase 13B — Credential Store + Refreshable Access-Token Foundation (completed)
- [x] Phase 13C — Google OAuth / Gmail Credential Lifecycle (completed)
- [x] Phase 13D — Microsoft Entra OAuth / Graph Credential Lifecycle (completed)
- [x] Phase 13E — Azure Key Vault + AWS Secrets Manager Production Backends (completed)
- [x] Phase 13F — Disconnect/Reauthorization, Production Hardening, Documentation & Regression (completed)

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

Owned disconnect sets `DISCONNECTED`, nulls `credential_ref`, and nulls `granted_capabilities`. Remaining grant metadata after the locator is removed would misrepresent the account. Google token revocation is best-effort after that local success. Microsoft uses local deletion only. See ADR-023.

## Account status

| Status | Meaning |
|---|---|
| `ACTIVE` | Credential operational / account eligible subject to capability checks |
| `DISCONNECTED` | User intentionally disconnected; ECI no longer possesses delegated credential material |
| `REAUTH_REQUIRED` | Confirmed permanent provider refresh failure; locator and last-known grants may remain for controlled cleanup; execution is blocked |

`REAUTH_REQUIRED` is not treated like `DISCONNECTED`. Transient credential-store or token-service unavailability does not change account status.
