# Phase 17 — Microsoft Entra External ID & External User Onboarding

## Objective

Move ECI product authentication from the current manually managed workforce-Entra customer-access model to Microsoft Entra External ID self-service customer signup/sign-in.

```text
External customer
→ External ID combined signup/sign-in (email OTP)
→ MSAL public client
→ ECI bearer access token
→ FastAPI single-issuer JWT validation
→ (iss, sub) → users.id
→ existing product APIs
→ independently connect Gmail and/or Outlook
```

Critical invariant:

```text
ECI APPLICATION LOGIN != MAILBOX LOGIN
```

External ID authenticates the person into ECI. Gmail OAuth independently connects Gmail mailboxes. Microsoft mailbox OAuth independently connects Outlook mailboxes. A customer's ECI login email or account may differ from every mailbox connected to that ECI user.

Architecture: [ADR-027](../decisions/ADR-027-microsoft-entra-external-id-customer-authentication.md).

## Status

Phase 17A is **Completed / PASS**. Phase 17B-A is **Completed / PASS**. Phase 17B-B is **Completed / PASS**. Phase 17B-C is **Completed / PASS**. Phase 17B-D is **Completed / PASS**. Phase 17B-E is **Completed / PASS**. Phase 17C is **Completed / PASS**. Phase 17C-G is **Completed / PASS** (this slice). Phase 17 overall is **Next**.

- **17A is Completed / PASS:** read-only External ID readiness assessment. No tenant, app registration, code, or documentation mutation in that slice.
- **17B-A is Completed / PASS:** ADR-027 and this roadmap lock the approved architecture. No authentication code, tenant, app registration, or migration.
- **17B-B is Completed / PASS:** frontend External ID / MSAL configuration uses explicit `VITE_ENTRA_AUTHORITY` and derived `knownAuthorities`. No live tenant.
- **17B-C is Completed / PASS:** backend External ID JWT / configuration. Existing single-issuer `TokenValidator` retained; CIAM-shaped offline tests added. No live tenant.
- **17B-D is Completed / PASS:** offline authentication, ownership, and mailbox-login-separation regression. No live IdP.
- **17B-E is Completed / PASS:** External ID development tenant, email OTP user flow, SPA/API registrations, five delegated scopes, and local ignored environment configuration. No Phase 17C product validation.
- **17C is Completed / PASS:** local External ID customer signup/sign-in, isolated internal user, one Outlook mailbox connect, bounded list, one Analyze, one Propose, one Approve. Send was not executed.
- **17C-G is Completed / PASS:** Gmail OAuth ID-token verification failed in 17C with `InvalidValue` after successful Google consent. Root cause was `google-auth` `verify_oauth2_token` default `clock_skew_in_seconds=0` against a drifting local/WSL clock, not Phase 17 identity architecture. A 60-second library leeway plus allowlisted `verify_error_reason` restored Gmail connect for the same External ID user. Send was not executed.
- **17D:** not started. Sally external verification starts only after 17C PASS.

Phase 16 remains **Completed**.

## Locked architecture

The following decisions are authoritative for Phase 17. They are recorded in ADR-027.

| Decision | Lock |
|---|---|
| Customer identity platform | Microsoft Entra External ID external/customer tenant |
| Workforce tenant | operator / admin / mailbox-OAuth / workload identity only; not long-term product login |
| Authentication approach | existing MSAL SPA, authorization code + PKCE, bearer tokens, FastAPI JWT validation |
| Initial sign-in method | email one-time passcode on the combined signup/sign-in user flow |
| Application identity key | verified `(iss, sub)` → `users.id` |
| Pairwise `sub` | External ID API registration is part of the durable identity boundary |
| Product-login cutover | exclusive External ID; no dual issuer |
| JWT validation | retain single-issuer `TokenValidator`; configure `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` |
| SPA authority | explicit CIAM authority; stop exclusive `login.microsoftonline.com/{tenant-id}` derivation |
| API permissions | retain `communications:read`, `analyze`, `connect`, `workflow`, `send` |
| Mailbox OAuth | unchanged identity semantics; Microsoft mailbox authority is not replaced |
| Schema | no Phase 17B migration; Alembic head remains `16f0001` |
| Hosting | same customer IdP on Azure and AWS |

Do not hardcode tenant-specific production values in source. Exact operator values come from the created tenant and OIDC discovery metadata.

External ID core MAU billing was confirmed immediately before 17B-E tenant creation. This roadmap does not quote pricing.

## 17A — External ID Readiness Assessment

**Completed / PASS.**

Read-only inventory of the current workforce-Entra product-login path, mailbox-login separation, JWT validator, `(iss, sub)` mapping, and SPA authority derivation. Recommended exclusive External ID cutover, retained identity key, and no schema migration. Implementation was deferred to 17B.

## 17B — External ID Implementation

Implementation is split into narrow slices based on the 17A assessment.

### 17B-A — ADR / Architecture Lock

**Completed / PASS.**

Persist the approved architecture before any implementation.

In scope:

- ADR-027
- this Phase 17 roadmap
- decisions and roadmap indexes

Out of scope:

- frontend or backend source
- tests
- migrations
- External ID tenant or app registrations
- Azure or AWS authentication
- commit or push

### 17B-B — Frontend External ID / MSAL Configuration

**Completed / PASS.**

- explicit `VITE_ENTRA_AUTHORITY` is the complete public MSAL authority
- `knownAuthorities` is derived from the authority hostname
- product login no longer constructs `https://login.microsoftonline.com/{tenant-id}`
- existing MSAL public-client, redirect, sessionStorage, and AuthContext model retained
- offline frontend tests updated; no live tenant or identity-endpoint contact

Do not rewrite the working MSAL stack. Do not implement mailbox OAuth in the SPA.

### 17B-C — Backend External ID JWT / Configuration

**Completed / PASS.**

- single-issuer `TokenValidator` unchanged: exact `iss`/`aud`, RS256, JWKS, `(iss, sub)`
- OIDC contract remains `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` and accepts CIAM-shaped values
- `.env.example` uses External ID placeholders; no real tenant values
- offline CIAM-shaped JWT tests added; no live discovery/JWKS contact
- no schema migration; mailbox OAuth unchanged

### 17B-D — Offline Authentication Regression

**Completed / PASS.**

- frontend CIAM authority / MSAL / scope regression holds
- backend exact-issuer JWT / `(iss, sub)` / permission regression holds
- ownership isolation and mailbox-login separation unchanged
- CI after 17B-C (`6425ed9`, run `33952384102`) passed the full offline matrix
- no live External ID, discovery, JWKS, Gmail, Outlook, Azure, or AWS dependency

### 17B-E — External ID Operator Setup

**Completed / PASS.**

Created the minimum development External ID identity environment on the existing ECI-Development subscription. No application source change. No schema migration. No mailbox OAuth change. Azure/AWS application runtimes were not resumed or deployed.

Safe resource metadata:

- tenant display name: `ECI External ID Development`
- tenant domain: `eciexternaliddev.onmicrosoft.com`
- tenant ID: `070eadae-1958-4b21-af42-3584ac284eba`
- SKU / billing: Base / A0, MAU (core External ID; no SMS, Go-Local, ID Governance, GSA, or M2M add-on)
- data location: Europe
- user flow: `ECI_SignUpSignIn_Dev` (combined sign-up/sign-in; Email OTP only)
- API registration: `eci-api-external-id-dev`
- SPA registration: `eci-web-external-id-dev`
- Application ID URI shape: `api://<api-client-id>`
- delegated scopes: `communications:read`, `communications:analyze`, `communications:connect`, `communications:workflow`, `communications:send`
- local redirect / post-logout: `http://localhost:5173`

Local ignored `.env` files now use the exact External ID issuer, JWKS URI, SPA client ID, and API audience from Microsoft discovery metadata. Tracked `.env.example` files remain placeholders. Product-login deploy templates now require `VITE_ENTRA_AUTHORITY` instead of `VITE_ENTRA_TENANT_ID`.

Do not treat email as the ECI durable identity. Recreating the API registration remains an identity-breaking event.

## 17C — Controlled External-User Validation

**Completed / PASS.**

Validated locally (Vite + FastAPI + existing local PostgreSQL) with an owner-controlled External ID customer account. No hosted Azure/AWS application runtime was resumed. Send was not authorized and was not executed.

Proven:

```text
External ID signup/sign-in (email OTP)
→ authenticated dashboard
→ new internal users.id for the CIAM (iss, sub)
→ one Microsoft Outlook mailbox connect
→ bounded first-page list
→ one synthetic/test message Analyze (MockAIProvider)
→ Propose (PENDING)
→ Approve (APPROVED)
→ STOP BEFORE SEND
```

Safe validation facts:

- product login used External ID CIAM; FastAPI accepted the exact CIAM issuer/audience
- no workforce-product-login fallback
- External ID user could not see prior workforce-owned connectors
- mailbox OAuth remained independent of ECI application login
- Gmail consent completed twice but ID-token verification failed (`InvalidValue`); verification was not weakened; Outlook was used instead
- approval did not send; Send remained a distinct unactivated control
- local ignored `.env` files were not committed

The sign-in experience now includes a short development/test privacy notice. External ID OTP placeholder display names such as `unknown` are ignored so the existing username fallback can be used.

Do not start Sally testing from this slice.

### 17C privacy boundary

The required short, plain-language test privacy/data-use notice is present on the ECI sign-in page.

This is a product/test prerequisite, not a full legal or compliance review. Do not write Sally-specific material in this phase.

## 17C-G — Gmail OAuth ID-Token Regression

**Completed / PASS.**

17C core validation remained PASS on Outlook. This slice investigated the Gmail callback failure after two successful Google consents.

Exact failure location: `GoogleMailboxOAuthClient._id_token_claims` → `google.oauth2.id_token.verify_oauth2_token` (google-auth 2.56.3). Token exchange had already succeeded (`id_token` and refresh token present). Verification stayed strict (signature, Google issuer, audience = Gmail OAuth client ID, expiry). Phase 17 application authentication did not change this path.

Root cause: library/runtime clock skew (`C`), not Phase 17 identity coupling. `verify_oauth2_token` used `clock_skew_in_seconds=0`. `InvalidValue` is the class google-auth raises for `iat`/`exp` leeway failures. The local WSL clock was observed 21 seconds off Google’s certs `Date` header. Gmail OAuth client ID, secret, localhost callback, requested scopes (`openid`, `gmail.readonly`, `gmail.send`), and in-memory credential store matched the Phase 16 contract. Verification was not weakened: no unverified decode, no email-as-identity, no audience bypass.

Fix: pass the documented 60-second `clock_skew_in_seconds` leeway and log an allowlisted `verify_error_reason` (`token_used_too_early`, `token_expired`, `wrong_audience`, `unsupported_algorithm`, `invalid_value`) without exception text or tokens.

Live retry on the same External ID session: Gmail callback succeeded; connector `2b61f24e-…` is `ACTIVE` with presentation-only display identity; durable Google `sub` is stored and not exposed publicly; connector belongs to CIAM user `f05c1ada-…`; workforce Gmail/Outlook connectors remained invisible (`result_count=2`); bounded Gmail first page (`maxResults=10`) returned 200. Outlook connector remained `ACTIVE`. Analyze / Propose / Approve were not repeated. Send was not executed.

Do not start Sally testing from this slice.

## 17D — Sally External Verification

Not started.

17D starts **only after 17C PASS**.

Later preparation may include a test URL, signup/sign-in instructions, the short privacy note, mailbox-connection instructions, a test/non-sensitive mailbox recommendation, the expected workflow, and a feedback path. That material is not written in 17B-A.

## Compatibility / cutover

No schema migration.

Application-auth configuration changes make mixed frontend/backend identity configurations fail closed with 401. Do not intentionally support a prolonged mixed state.

Recommended later cutover:

1. External ID tenant, user flow, and applications are created.
2. Code capable of an explicit CIAM authority is deployed and tested.
3. Backend OIDC configuration and SPA External ID configuration are switched together per environment.
4. External login is validated.
5. Test mailboxes are reconnected under the new External ID internal ECI user.

Workforce product login is then retired. Do not delete workforce tenant resources required for operations or mailbox OAuth.

Existing workforce-mapped ECI users may remain in PostgreSQL and become unreachable after issuer cutover. No identity linking or data migration is required for current development data.

## Non-goals

- dual workforce + External ID product login
- account linking
- migrating workforce ECI identities into External ID identities
- email as durable ECI identity
- social login
- Google login as ECI login
- Microsoft personal-account login as a separate provider
- enterprise federation
- organizations / teams
- invitations
- billing / subscriptions
- custom ECI password storage
- mailbox-login / application-login merging
- new mailbox identity semantics
- automatic replies
- worker / sync architecture
- a new workflow state machine
- retry / outbox / `EXECUTION_UNKNOWN`
- full 2×2×2 cloud / mailbox / AI certification
- HA / DR / private networking
- Sally testing before 17C passes

## Current Microsoft product assumptions

This phase assumes Microsoft Entra External ID external tenants support customer self-service sign-up/sign-in with email one-time passcode.

Operator values come from the created tenant and OIDC discovery metadata. Portal navigation is not specified here. Pricing is not quoted here.
