# ADR-013: External Identity Mapping and User-Owned Data

## Status

Accepted

The decision is implemented. Phase 9B maps a verified OIDC `(issuer, subject)` to an opaque internal `users.id` UUID and scopes analysis history to that UUID. Phase 9 does not implement SaaS tenancy.

## Date

Phase 9 (Persistence)

## Context

Phase 8 authenticates callers with a provider-independent OIDC JWT. Authorization requires permission `communications:analyze`. That is sufficient to protect analyze, but not sufficient to own stored history.

A persisted identity model must:

- uniquely identify a caller across requests
- avoid treating email as a stable identifier
- remain independent of a specific identity provider SDK
- isolate one user's history from another
- leave room for future organizations without pretending they exist now

`sub` alone is not unique across issuers. The same subject string can appear at more than one identity provider. Email can be reused, changed, or missing from an access token.

## Decision

Treat `(issuer, subject)` as the external identity unique key and map it to an internal user UUID.

```text
OIDC JWT
→ TokenValidator (iss, aud, exp, JWKS, permission)
→ AuthenticatedPrincipal (issuer, subject)
→ IdentityResolver
→ users.id UUID
→ owned analyses
```

Persisted identity data:

- `issuer`
- `subject`

Not persisted:

- email
- name
- display name
- profile picture
- JWT
- Authorization header
- access token
- refresh token
- scope or role claims

Ownership queries always include `user_id` in SQL. Unknown and cross-user analysis resources return `404` with `{"detail": "Analysis not found."}`, not `403`. History endpoints reuse `communications:analyze`; they do not introduce a second permission.

### SaaS tenancy boundary

Phase 9 provides **user-associated ownership isolation**.

Phase 9 does **not** provide:

- SaaS organizations
- tenants
- workspaces
- membership
- tenant roles
- tenant-wide data sharing
- multi-tenant enterprise RBAC
- shared inbox ownership

Multiple authenticated users are not full multi-tenancy.

### Future tenant readiness

The internal UUID can remain the stable identity foreign key if organizations are added later:

```text
users
  ↓
memberships
  ↓
organizations / workspaces
```

Those tables are not created in Phase 9. Future compatibility is not currently implemented tenancy. Future connector resources can also reference `users.id`. See Phase 10 compatibility in [Persistence architecture](../architecture/persistence.md).

## Alternatives Considered

- **Use JWT `sub` as the database primary key** — rejected. Subjects are issuer-scoped.
- **Use email as the ownership key** — rejected. Email is not always present, is not unique across issuers, and is PII.
- **Store profile claims for display** — rejected. Phase 9 only needs an opaque ownership key.
- **Return 403 for cross-user resources** — rejected. That confirms that a resource exists for another user.

## Consequences

- The same person at two issuers is two internal users until an explicit linking design exists.
- History is empty until the caller has been mapped, which happens on first successful persist-after-analyze path.
- Application-user authentication remains OIDC. Internal users are not a login system.

## Benefits

- stable ownership key independent of IdP representation
- no email identifier
- IDOR-safe 404 semantics
- future membership tables can attach to `users.id` without rewriting analysis ownership

## Trade-offs

- no organization sharing in this phase
- no account linking across issuers
- history endpoints always require an authenticated principal; `AUTH_MODE=disabled` returns `401` and remains analyze-only

## Deferred Work

- organizations, workspaces, and memberships
- tenant RBAC
- shared mailbox or connector-team ownership
- account linking across identity providers

## Related Components

- `app/application/services/identity.py`
- `app/application/services/analysis_history.py`
- `app/api/routes/analyses.py`
- ADR-009 (Application-User Authentication)
- ADR-012 (PostgreSQL Persistence Architecture)
