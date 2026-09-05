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

Phase 17A is **Completed / PASS**. Phase 17B-A is **Completed / PASS**. Phase 17B-B is **Completed / PASS** (this slice). Phase 17 overall is **Next**.

- **17A is Completed / PASS:** read-only External ID readiness assessment. No tenant, app registration, code, or documentation mutation in that slice.
- **17B-A is Completed / PASS:** ADR-027 and this roadmap lock the approved architecture. No authentication code, tenant, app registration, or migration.
- **17B-B is Completed / PASS:** frontend External ID / MSAL configuration uses explicit `VITE_ENTRA_AUTHORITY` and derived `knownAuthorities`. No live tenant.
- **17B-C is Next:** backend External ID JWT / configuration.
- **17B-D:** offline authentication regression.
- **17B-E:** External ID operator setup, only after separate explicit authorization.
- **17C:** not started. Controlled owner-account validation after 17B.
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

Do not hardcode tenant-specific production values in source. Exact operator values come from the later tenant and OIDC discovery metadata.

Confirm External ID cost immediately before 17B-E. This roadmap does not quote pricing.

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

**CURRENT SLICE. Completed / PASS.**

- explicit `VITE_ENTRA_AUTHORITY` is the complete public MSAL authority
- `knownAuthorities` is derived from the authority hostname
- product login no longer constructs `https://login.microsoftonline.com/{tenant-id}`
- existing MSAL public-client, redirect, sessionStorage, and AuthContext model retained
- offline frontend tests updated; no live tenant or identity-endpoint contact

Do not rewrite the working MSAL stack. Do not implement mailbox OAuth in the SPA.

### 17B-C — Backend External ID JWT / Configuration

Next implementation slice.

- retain the single-issuer `TokenValidator`
- document and accept an External ID configuration contract (`OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`)
- add CIAM-shaped offline JWT tests
- no schema migration
- no dual-issuer validator

### 17B-D — Offline Authentication Regression

- frontend tests
- backend tests
- ownership isolation regression
- mailbox-login separation regression
- no live IdP dependency in CI

### 17B-E — External ID Operator Setup

Operator/configuration slice. Do not perform it without a separate explicit authorization.

Expected later work:

- create an External ID development tenant
- create the customer sign-up/sign-in user flow
- enable email OTP
- create the SPA registration
- create the API registration
- expose the five existing ECI scopes
- register localhost redirects and logout URIs

This slice is cost-bearing. Confirm current External ID pricing before creation. 17B-B through 17B-D can complete offline without a live tenant. Live signup cannot.

## 17C — Controlled External-User Validation

Not started.

Use an account controlled by the owner. Do not start Sally testing.

Expected path:

```text
signup
→ sign in
→ ECI dashboard
→ independently connect Gmail or Outlook
→ mailbox list
→ Analyze
→ Propose
→ Approve
→ optional separately authorized Send
```

Must verify:

- ECI application identity != mailbox identity
- user / connector isolation

### 17C privacy boundary

Before 17C live external-user testing, ECI should provide a short, plain-language test privacy/data-use notice.

This is a product/test prerequisite, not a full legal or compliance review. Do not write Sally-specific material in this phase.

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
