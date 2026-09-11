# ADR-028: Platform Owner Identity and Application RBAC

## Status

Accepted

The Solution Architect locked this decision in Phase 19A. Phase 19B–19F implemented schema, `require_owner`, operator bootstrap, `/me`, frontend awareness, and security/documentation closure under this ADR. This ADR does not itself mutate Entra, Azure, or AWS resources, and it does not perform real owner activation.

This ADR does not rewrite [ADR-009](ADR-009-application-user-authentication.md), [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md), [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md), [ADR-025](ADR-025-browser-frontend-and-authentication-architecture.md), or [ADR-027](ADR-027-microsoft-entra-external-id-customer-authentication.md). It adds application-persisted owner RBAC on top of the existing External ID product-login and `(iss, sub)` mapping contracts.

## Date

Phase 19 (Platform Owner Identity & Application RBAC)

## Context

Through Phase 18, every authenticated External ID principal is an ordinary application user. The API authorizes capability via OIDC permission strings (`communications:*` from `scp` / `scope` / `roles`) and scopes persisted resources by internal `users.id`. There is no platform owner or application-admin role.

The product now needs a minimal, server-authoritative way to designate one or more platform owners without:

- changing ordinary External ID signup/sign-in
- granting privilege from email or mailbox identity
- treating Microsoft Entra JWT `roles` as ECI application RBAC
- coupling application RBAC to Azure RBAC, AWS IAM, Foundry, or Bedrock
- introducing an admin dashboard in the initial Phase 19 scope

Phase 19 architecture/readiness assessment reported **READY WITH PREREQUISITES**. Phase 18 remains **CLOSED / PASS**.

## Problem

ECI must answer, for a verified product-login principal:

```text
Is this authenticated application user a platform owner?
```

That answer must be:

- bound to the immutable trusted identity already used for ownership
- persisted and enforced by the server
- independent of mailbox OAuth identities
- identical on Azure-hosted and AWS-hosted ECI
- impossible to obtain through normal signup alone

## Decision

Adopt **Approach A**: an existing Microsoft Entra External ID application user may be explicitly designated as the ECI platform owner.

Persist ECI application RBAC in the application database. Prefer an initial constrained `users.application_role` column with values `user` | `owner`, default `user`.

Bind owner identity to the immutable trusted identity tuple already established by ADR-013 / ADR-027:

```text
(verified JWT issuer, verified JWT subject)
=
(iss, sub)
```

After mapping, authorization evaluates the internal `users.id` row's `application_role`. Email, display name, `preferred_username`, Gmail identity, Outlook/Graph mailbox identity, and other mailbox attributes must never grant owner status.

```text
External ID product login
→ verified (iss, sub)
→ users.id
→ application_role: user | owner
→ server-side require_owner (or equivalent)
```

Initial role model:

```text
user
owner
```

All existing users and all future normal signups remain `user` unless explicitly promoted through the controlled owner bootstrap in a later slice. `resolve_or_create` / normal signup must never automatically create an owner.

## Immutable identity anchor

The only durable owner anchor is:

```text
verified token iss
+
verified token sub
```

Do not use as owner/admin security identity:

- email address
- display name
- preferred_username
- Gmail mailbox identity
- Outlook / Microsoft Graph mailbox identity
- other mailbox attributes
- client-supplied role headers or body fields
- Foundry / Bedrock / Azure RBAC / AWS IAM principals

Presentation claims remain presentation-only when shown. They are not owner keys.

### No real owner identity in tracked artifacts

Tracked documentation and source code must not contain real owner `(iss, sub)` values, real access tokens, or other secrets.

Capture and promotion of a real owner identity happen only through a controlled operator step (Phase 19D CLI). Placeholders in examples remain conceptual. Real activation is environment-specific and outside tracked source.

## Application-role persistence

Preferred initial persistence:

```text
users.application_role
  constrained to: user | owner
  default: user
```

Consequences for later slices:

- additive Alembic migration backfills existing rows to `user`
- create / `resolve_or_create` always writes `user`
- promotion is an explicit operator-controlled bootstrap action
- a separate `user_roles` assignment table is deferred until multi-role needs appear

ECI application RBAC is server-authoritative and persisted in the application database. The database role is the authorization source of truth for owner checks.

## Separation from OAuth permission scopes

Existing communications permission handling remains separate and unchanged by this decision:

```text
communications:read
communications:analyze
communications:connect
communications:workflow
communications:send
```

Microsoft Entra JWT `roles` must **not** be treated as ECI application RBAC in this phase. Token `roles` / `scp` / `scope` continue to supply capability permissions only. Owner status is not inferred from those claims.

Owner authorization is additive to ordinary capability checks. It does not replace `communications:*` permission gates.

## Separation from mailbox identities

Gmail and Microsoft Graph mailbox OAuth identities remain completely separate from application owner identity.

```text
ECI APPLICATION LOGIN / OWNER ROLE
!=
MAILBOX LOGIN
```

Mailbox connect, reconnect, disconnect, read, analyze, and send paths must not consult `application_role` to authorize mailbox access, and must not promote application role from mailbox identity.

## Secure bootstrap principle

First-owner designation is an explicit, auditable operator action in a later slice. It is not silent signup.

Required principles:

1. Designated human signs in through ordinary External ID → mapping creates an ordinary `user`.
2. Operator captures the verified `(iss, sub)` for that environment through a controlled step.
3. Controlled bootstrap promotes that mapped user to `owner`.
4. No public self-assignment API.
5. No email allowlist promotion.
6. No "first user wins" race.
7. No automatic promotion inside `resolve_or_create`.

Optional later hardening may use Settings allowlists solely to constrain the bootstrap command. Allowlists must not auto-promote on every authenticated request unless a later explicit decision designs a one-time, audited mechanism.

## Backend and frontend authorization boundary

Backend authorization provides a server-side `require_owner` guard. The minimal admin probe (`GET /api/v1/admin/ping`) enforces that guard. No admin dashboard is part of the initial Phase 19 scope.

Frontend role awareness comes from server-authoritative `GET /api/v1/me`. Frontend visibility is never security enforcement. The SPA must not grant privileges from MSAL token `roles` or `scp`.

## Multi-cloud implications

Azure-hosted and AWS-hosted ECI must use the same application RBAC design.

- same role model and persistence shape
- same `(iss, sub)` identity anchor
- same server-side owner guard semantics
- same bootstrap principle per environment database

Application RBAC is not Azure RBAC, not AWS IAM, not Foundry authorization, and not Bedrock authorization. Cloud workload identities remain operator/runtime concerns and are not application owner sources.

## Deferred workforce federation

Workforce-Entra → External-ID federation remains a possible long-term enhancement. It is **out of scope** for the initial Phase 19 implementation.

Ordinary External ID users already produce the durable `(iss, sub)` ECI trusts. The workforce tenant remains the operator / admin / mailbox-OAuth / workload directory per ADR-027. It is not reintroduced as the product-login owner directory for Phase 19.

## Future extensibility

This decision leaves room for later work without requiring it now:

- additional application roles beyond `user` / `owner`
- a normalized role-assignment table if multi-role assignments become necessary
- optional later IdP claim sync **only if** the database remains authoritative
- workforce → External ID federation as a separate identity project
- admin product surfaces after server-side owner authorization exists

Do not implement those extensions in the initial Phase 19 slices unless explicitly instructed.

## Alternatives Considered

- **Approach A — Designate an existing External ID application user as owner** — **selected**. Fits the current single-issuer External ID product login, reuses trusted `(iss, sub)`, needs no Entra federation for v1, and works identically on Azure and AWS hosts.
- **Approach B — Federate workforce identity into External ID, then apply app RBAC** — deferred. Valid long-term identity hygiene for some organizations, but ADR-027 already deferred enterprise federation. It adds Entra project work and subject-stability risk not required to ship owner authorization.
- **Approach C — Config-only allowlist of `(iss, sub)` with no database role** — rejected as the sole authorization model. Acceptable only as optional bootstrap hardening later. Weak for audit, `/me`, multi-owner evolution, and durable authorization truth.
- **Entra app roles alone as ECI application RBAC** — rejected. Creates IdP lock-in, local/CI friction, and conflates existing JWT `roles` permission extraction with application owner status.
- **Email / display-name / preferred_username allowlist** — rejected. Mutable presentation data; not the durable identity key.
- **Mailbox identity as owner key** — rejected. Violates application-login ≠ mailbox-login.
- **Automatic first signup becomes owner** — rejected. Race-prone privilege escalation.
- **Frontend-enforced admin UI as security** — rejected. UX only; server must enforce.

## Security consequences

- Ordinary signup cannot become owner.
- Email equality cannot grant owner status.
- Same email with a different `sub` is a different user and is not owner unless separately promoted.
- Mailbox OAuth cannot satisfy owner authorization.
- Client-supplied role values are ignored for authorization.
- JWT `roles` remain communications-permission input, not application RBAC.
- Recreating the External ID API registration remains an identity-breaking event (pairwise `sub`); owner binding must be re-established after such a break.
- Admin APIs must not accidentally widen cross-user data access without an explicit later design.
- Tracked docs/source must never embed real owner `(iss, sub)` values.

## Operational consequences

- Slice 19B added the safe role schema/migration.
- Slice 19C added server-side `require_owner`.
- Slice 19D delivered controlled first-owner bootstrap (CLI); real activation remains operator-executed per environment.
- Slice 19E exposed server-authoritative `/me` and frontend awareness.
- Slice 19F closed with a security regression matrix and documentation.
- No Microsoft Entra, Azure, or AWS resource changes are required for Approach A architecture lock.
- No admin dashboard in initial Phase 19 scope.

## Non-goals

Phase 19 initial scope does not include:

- implementing RBAC code in 19A
- database migration in 19A
- admin dashboard
- workforce → External ID federation
- treating Entra JWT `roles` as application RBAC
- changing mailbox OAuth semantics
- changing Foundry / Bedrock / Azure RBAC / AWS IAM as application role sources
- organizations / teams / SaaS tenancy
- capturing real owner `(iss, sub)` into tracked documentation or source

## Benefits

- reuses the existing trusted identity contract
- keeps ordinary customer signup unchanged and non-privileged
- remains provider- and host-neutral across Azure and AWS
- separates capability scopes from application owner status
- preserves mailbox-login isolation

## Trade-offs

- first owner requires a controlled operator bootstrap per environment
- pairwise External ID `sub` means API-registration replacement breaks owner binding
- two-role column is simple now and may need generalization later
- no admin product UI in the initial phase

## Related Components

- `app/application/services/identity.py` (create path remains non-owner)
- `app/application/services/owner_bootstrap.py` (operator first-owner promotion)
- `app/cli/promote_owner.py` (operator CLI; no HTTP role mutation)
- `app/core/security.py` (communications permissions remain separate)
- `app/infrastructure/storage/models.py` (`application_role`)
- `app/api/dependencies.py` (`require_owner`)
- `app/api/routes/me.py` / `app/schemas/me.py` (`GET /api/v1/me`)
- `app/api/routes/admin.py` (minimal owner probe)
- [ADR-009](ADR-009-application-user-authentication.md)
- [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md)
- [ADR-025](ADR-025-browser-frontend-and-authentication-architecture.md)
- [ADR-027](ADR-027-microsoft-entra-external-id-customer-authentication.md)
- [Phase 19](../roadmap/phase-19-platform-owner-identity-and-application-rbac.md)
