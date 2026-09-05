# ADR-027: Microsoft Entra External ID for Customer Authentication

## Status

Accepted

The Solution Architect locked this decision in Phase 17B-A. Implementation, tenant creation, and app registration are later 17B slices. Historical workforce-Entra product login remains in the current codebase until the exclusive configuration cutover.

This ADR does not rewrite [ADR-009](ADR-009-application-user-authentication.md), [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md), [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md), [ADR-025](ADR-025-browser-frontend-and-authentication-architecture.md), or [ADR-026](ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md). It narrows their workforce-product-login assumptions for Phase 17 onward.

## Date

Phase 17 (Microsoft Entra External ID & External User Onboarding)

## Context

Through Phase 16, ECI product login uses a manually managed workforce Microsoft Entra tenant. The SPA derives authority as `https://login.microsoftonline.com/{tenant-id}`. FastAPI validates a single issuer, audience, and JWKS URL. Verified `(iss, sub)` maps to an internal `users.id` UUID.

That model works for developer and operator validation. It is not a customer-facing signup path. Ordinary customers should not require a manual invitation into the workforce tenant.

Phase 17A assessed readiness and reported PASS. The remaining product requirement is self-service customer signup/sign-in while preserving the existing identity-domain split:

```text
ECI APPLICATION LOGIN != MAILBOX LOGIN
```

External ID authenticates the person into ECI. Gmail OAuth independently connects Gmail mailboxes. Microsoft mailbox OAuth independently connects Outlook mailboxes. A customer's ECI login email or account may differ from every mailbox connected to that ECI user.

## Decision

Move ECI product authentication from the current workforce-Entra customer-access model to Microsoft Entra External ID in a dedicated external/customer tenant.

Retain the existing browser-delegated MSAL SPA architecture, authorization code + PKCE, bearer access tokens, and single-issuer FastAPI JWT validation. Adopt External ID primarily through configuration. Do not introduce a custom ECI password or session system.

The initial customer sign-in method is email one-time passcode on the External ID combined sign-up/sign-in user flow.

Keep `(issuer, subject)` as the application-user identity key. Do not implement dual-issuer trust. Do not add a Phase 17 schema migration.

## Identity-domain separation

These identity classes remain separate:

1. **ECI application user** — External ID OIDC JWT → `AuthenticatedPrincipal` → `users.id`
2. **Gmail mailbox identity** — verified Google durable identity on the mailbox OAuth path
3. **Microsoft mailbox identity** — existing Microsoft mailbox durable identity on the mailbox OAuth path
4. **Cloud workload identity** — Foundry Managed Identity / Bedrock task role
5. **Database identity** — `DATABASE_URL` credentials
6. **Deployment / operator identity** — GitHub OIDC, Azure/AWS administration, Key Vault administration

The ECI API bearer token must never become a mailbox credential. Mailbox OAuth credentials must never authenticate to the ECI REST API.

## Authentication approach

Retain the Phase 15 / ADR-025 browser architecture:

```text
Browser
→ React / Vite SPA
→ MSAL public client
→ authorization code + PKCE
→ External ID access token
→ FastAPI Authorization: Bearer
→ TokenValidator
→ IdentityResolver
→ users.id
```

Do not add:

- a backend-for-frontend
- application session cookies
- a frontend client secret
- an ECI-issued password store
- an ECI-managed session database

Frontend permission helpers may continue to inspect `scp` for UX. Backend token validation remains authoritative.

## External ID customer-tenant choice

ECI customer accounts must not require manual invitation into the existing workforce Entra tenant. The External ID external/customer tenant is the long-term ECI product-login directory.

The existing workforce tenant continues to serve operator and administrative purposes, including:

- Azure administration
- deployment / operator identity
- managed / workload identity
- Microsoft Foundry administration
- Key Vault administration
- the existing Microsoft mailbox OAuth application where applicable

It is not the long-term ECI customer-login directory.

Workforce product-login app registrations used through Phase 16 (`eci-web-dev`, `eci-api-auth-dev`) are not the customer-facing External ID applications. Do not delete workforce tenant resources required for operations or mailbox OAuth merely because product login moves.

## Email OTP choice

The selected Phase 17 initial customer path is email one-time passcode.

Use the External ID combined sign-up/sign-in user flow. The existing Sign in entry point remains the signup/sign-in entry point.

Phase 17 does not add:

- social identity providers
- enterprise federation
- Google login as ECI login
- Microsoft personal-account login as a separate ECI provider
- a username/password implementation inside ECI

Email/password may remain a future External ID configuration alternative. It is not the selected Phase 17 initial customer path. Do not build both OTP and password paths into ECI application code.

Exact operator values come from the created tenant and OIDC discovery metadata later. This ADR does not hardcode tenant-specific production values or portal navigation.

External ID cost and monthly active users must be confirmed immediately before the future tenant-creation slice. Pricing is operational and time-sensitive. This ADR does not quote pricing.

## `(iss, sub)` identity-key decision

Retain the ADR-013 mapping:

```text
verified token iss
+
verified token sub
→
internal users.id UUID
```

Do not use email as a security identity. Do not use display name as a security identity. Do not switch to `oid` in Phase 17.

Email, name, and preferred username remain presentation-only when shown. They are not persisted as identity keys.

## Pairwise-sub consequence

External ID `sub` is pairwise to the application/resource context.

The External ID API application registration is therefore part of the durable identity boundary. Recreating or replacing that API registration can change subject values and can make existing `external_identities` mappings unreachable.

Phase 17 does not implement account linking or identity migration between recreated app registrations. Operators must treat replacement of the External ID API registration as an identity-breaking action.

An alternative architecture could use `oid` for cross-application stability. Adopting it would reopen the existing identity contract and is deliberately out of Phase 17 scope.

## Exclusive cutover / no dual issuer

External ID becomes the ECI product-login identity provider.

Phase 17 does not implement dual workforce + External ID issuer trust in the product API.

Reasons:

- avoids two token trust roots
- avoids two internal users for the same human
- avoids retaining manually invited workforce customers as product-login principals
- keeps the authorization model a single issuer, audience, and JWKS
- local and CI development do not require live workforce product login

Existing workforce-mapped ECI users may remain in PostgreSQL and become unreachable after product-auth issuer cutover. No identity linking or data migration is required for current development data.

## JWT validation strategy

Retain the current single-issuer `TokenValidator` architecture:

- exact issuer
- exact audience
- RS256 only
- JWKS
- required `exp`, `iss`, `aud`, `sub`
- existing `scp` / `scope` / `roles` permission authorization

External ID is adopted primarily through configuration:

```text
OIDC_ISSUER
OIDC_AUDIENCE
OIDC_JWKS_URL
```

Do not create a dual-issuer validator. Mixed frontend/backend identity configurations must fail closed with 401. Do not intentionally support a prolonged mixed state.

Exact issuer, audience, and JWKS values come from later operator setup and discovery metadata. Source placeholders remain conceptual.

## SPA / MSAL authority strategy

Phase 17B must stop deriving authority exclusively as:

```text
https://login.microsoftonline.com/{tenant-id}
```

Introduce explicit External ID authority configuration. Expected conceptual form:

```text
https://{tenant-subdomain}.ciamlogin.com/...
```

MSAL must be configured for the External ID authority, including `knownAuthorities` where required. Retain the current MSAL public-client abstraction. Do not rewrite the working authentication stack.

Exact operator values must come from the created tenant and OIDC discovery metadata later. Do not hardcode tenant-specific production values in source.

## API resource / scopes

The External ID customer tenant will require:

- a SPA application registration
- an API resource application registration
- v2 access tokens
- the existing ECI delegated permission names

Retain:

```text
communications:read
communications:analyze
communications:connect
communications:workflow
communications:send
```

These are ECI application permissions. They are not Gmail scopes. They are not Microsoft Graph `Mail.Read` / `Mail.Send` scopes. Do not rename or weaken them.

The frontend scope identifiers continue to use the `api://` application-ID-URI shape. Audience remains the API application identifier after validation.

## Mailbox OAuth separation

Phase 17 must not modify mailbox identity semantics.

Preserve:

- Gmail: verified Google durable identity
- Outlook: existing Microsoft mailbox durable identity
- connector ownership by internal `users.id`
- exact-account reconnect
- Connect Another
- multiple same-provider connectors
- presentation-only `display_identity`
- mailbox durable identifiers remaining internal
- independent Gmail and Outlook OAuth

The Microsoft mailbox OAuth authority must not be replaced merely because ECI application login moves to External ID. Mailbox OAuth remains the server-side ADR-021 transaction.

## Persistence / schema consequence

No Phase 17B schema migration.

Current Alembic head `16f0001` and existing:

```text
external_identities(issuer, subject) → users.id
```

are sufficient.

Do not add:

- `identity_provider`
- email identity keys
- account linking
- customer profile tables

unless a later explicit architecture decision requires them.

## Azure / AWS hosting independence

External ID is the ECI application identity provider. It must work whether ECI is hosted on Azure or AWS.

Do not couple customer identity to Azure hosting. Both hosted environments should eventually consume the same customer IdP configuration. Hosting topology remains ADR-026. Mailbox credential stores remain Key Vault on Azure and Secrets Manager on AWS.

## Alternatives Considered

- **Continue invited workforce users** — rejected. It cannot provide self-service customer signup and keeps ordinary customers inside the operator tenant.
- **B2B guest-based customer access** — rejected. Guests still depend on invitation or cross-tenant administration. That is not customer self-service signup.
- **Dual workforce + External ID issuer** — rejected. It creates two trust roots, two possible internal users for one human, and a more complex authorization model. Local and CI already authenticate without live workforce product login.
- **External ID email/password as the Phase 17 initial path** — rejected for the initial customer path. Email OTP is the selected first method. Password may remain a later External ID configuration choice. ECI must not implement both paths in application code.
- **Another CIAM platform such as Auth0 or Cognito** — rejected for Phase 17. The architect selected Microsoft Entra External ID. The API is already provider-independent OIDC; changing CIAM vendor would add a new operational platform without changing the locked identity contract.
- **Change the ECI application identity key from `sub` to `oid`** — rejected for Phase 17. `oid` can be more stable across application registrations, but adopting it would reopen ADR-013. Pairwise `sub` is accepted as an operator constraint.

## Security consequences

- Product login has one token trust root after cutover.
- Email remains mutable presentation data, not a durable principal.
- Recreating the External ID API registration is an identity-breaking event.
- Workforce-mapped development users become unreachable after issuer cutover; that is accepted.
- Mixed SPA/API IdP configuration fails closed.
- Signup abuse, enumeration, and OTP delivery remain primarily External ID concerns.
- The API continues to trust bearer-token expiry only. There is no ECI token-revocation list.
- Mailbox tokens remain isolated in the credential store.

## Operational consequences

- A later authorized slice must create the External ID development tenant, combined user flow, email OTP, SPA registration, API registration, five scopes, and localhost redirect/logout URIs.
- SPA and backend product-auth configuration must switch together per environment.
- After cutover, test mailboxes must be reconnected under the new External ID internal ECI user.
- Workforce tenant resources required for operations and mailbox OAuth are retained.
- Azure and AWS later consume the same customer IdP values; only frontend origin/redirect and API base URL differ by host.
- Confirm External ID cost immediately before tenant creation.

## Non-goals

Phase 17 does not include:

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

## Migration / cutover implications

No schema migration. Application-auth configuration changes make mixed frontend/backend identity configurations fail closed with 401.

Recommended later cutover:

1. External ID tenant, user flow, and applications are created.
2. Code capable of an explicit CIAM authority is deployed and tested.
3. Backend `OIDC_*` configuration and SPA External ID configuration are switched together per environment.
4. External login is validated.
5. Test mailboxes are reconnected under the new External ID internal ECI user.

Workforce product login is then retired. Workforce tenant resources required for operations or mailbox OAuth are not deleted.

Before 17C live external-user testing, ECI should provide a short, plain-language test privacy/data-use notice. That is a product/test prerequisite, not a full legal or compliance review.

## Benefits

- customers can sign up without workforce-tenant invitation
- existing MSAL, JWT, permission, and ownership architecture is reused
- mailbox identity remains independent of product login
- Azure and AWS can share one customer IdP
- local and CI stay offline-capable

## Trade-offs

- current workforce-mapped product users become unreachable after cutover
- pairwise `sub` makes the API registration part of the identity boundary
- operators must provision a customer tenant and two External ID applications
- mixed IdP configuration is intentionally unsupported

## Related Components

- `app/core/security.py`
- `app/core/config.py`
- `app/application/services/identity.py`
- `frontend/src/auth/msal.ts`
- `frontend/src/config/env.ts`
- [ADR-009](ADR-009-application-user-authentication.md)
- [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md)
- [ADR-025](ADR-025-browser-frontend-and-authentication-architecture.md)
- [ADR-026](ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md)
- [Phase 17](../roadmap/phase-17-external-id-external-user-onboarding.md)
