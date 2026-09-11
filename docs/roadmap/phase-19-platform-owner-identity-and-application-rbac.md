# Phase 19 — Platform Owner Identity & Application RBAC

## Objective

Introduce a minimal, server-authoritative platform owner role for ECI without changing ordinary External ID customer authentication or mailbox OAuth flows.

```text
External ID application user
→ verified (iss, sub)
→ users.id
→ application_role: user | owner
→ server-side require_owner
→ later owner-aware APIs / UX
```

Critical invariants:

```text
ECI APPLICATION LOGIN != MAILBOX LOGIN
owner status != email / display name / mailbox identity
owner status != Entra JWT roles / communications:* scopes
Azure-hosted RBAC design == AWS-hosted RBAC design
```

Architecture: [ADR-028](../decisions/ADR-028-platform-owner-identity-and-application-rbac.md).

## Status

Phase 19 architecture/readiness assessment: **READY WITH PREREQUISITES**.

| Item | Status |
|---|---|
| Phase 18 — Secure Attachment Intelligence | **CLOSED / PASS** (unchanged) |
| Phase 19 assessment | READY WITH PREREQUISITES |
| **19A** Architecture decision lock | **CLOSED / PASS** |
| **19B** Role schema/model + safe migration | **CLOSED / PASS** |
| **19C** Server-side owner authorization | **CLOSED / PASS** |
| **19D** Secure first-owner bootstrap | **CLOSED / PASS** |
| **19E** `/me` + frontend owner awareness | **CLOSED / PASS** |
| **19F** Security regression matrix + documentation closure | Not started |
| Phase 19 overall | Next (19A–19E complete) |

Phase 18 remains **CLOSED / PASS**. Phases 19A–19E remain **CLOSED / PASS**. Do not reopen or rewrite completed phases.

**Important:** the controlled first-owner bootstrap command exists, but **real owner activation has NOT occurred** in this slice. No real `(iss, sub)` values were captured or stored in the repository. Operators must run promotion later against an environment database after ordinary External ID sign-in.

## Locked architecture

The following decisions are authoritative for Phase 19. They are recorded in ADR-028.

| Decision | Lock |
|---|---|
| Phase name | Platform Owner Identity & Application RBAC |
| Initial approach | Approach A — designate an existing External ID application user as owner |
| Identity anchor | verified `(iss, sub)` only |
| Persistence | constrained `users.application_role`, default `user` |
| Initial roles | `user`, `owner` |
| Normal signup | always `user`; never auto-owner |
| Entra JWT `roles` | not ECI application RBAC; `communications:*` remains separate |
| Authorization | server-side `require_owner` / equivalent |
| Frontend awareness | server-authoritative `/me` later; UX only, not enforcement |
| Mailbox OAuth identities | completely separate from owner identity |
| Foundry / Bedrock / Azure RBAC / AWS IAM | not application RBAC sources |
| Multi-cloud | same application RBAC design on Azure and AWS hosts |
| Workforce → External ID federation | deferred; out of initial Phase 19 scope |
| Admin dashboard | out of initial Phase 19 scope |

### Identity and documentation safety

- No real owner `(iss, sub)` value belongs in tracked documentation or source code.
- Owner identity is promoted only through the controlled operator bootstrap (`python -m app.cli.promote_owner`); real activation is environment-specific and outside git.
- Examples and placeholders remain conceptual.

## 19A — Architecture decision lock

**Completed / PASS.**

Persist the approved architecture before any implementation.

In scope:

- ADR-028
- this Phase 19 roadmap
- decisions and roadmap indexes

Out of scope:

- RBAC application code
- database migration
- admin endpoints
- Microsoft Entra changes
- Azure or AWS resource changes
- capturing or storing real owner identity values
- commit or push

## 19B — Role schema/model + safe migration

**Completed / PASS.**

Implemented the persistence/domain foundation only.

Delivered:

- Alembic revision `19b0001` (down_revision `18d0001`)
- additive portable text column `users.application_role`
- values constrained to `user` | `owner` via `ck_users_application_role`
- server/ORM default `user`; existing rows migrate to `user`
- domain `ApplicationRole` StrEnum
- `create_user_with_external_identity` / `resolve_or_create` always persist `user`
- no owner promotion API, admin routes, `/me`, frontend awareness, or Entra changes

Out of scope (deferred):

- `require_owner` (19C)
- secure first-owner bootstrap / promotion (19D)
- `/me` + frontend owner awareness (19E)
- admin dashboard
- workforce federation

## 19C — Server-side owner authorization

**Completed / PASS.**

Implemented server-side owner authorization only.

Delivered:

- `IdentityRepository.get_application_role_for_user(user_id)`
- FastAPI `require_owner` dependency (DB `application_role` only after verified `(iss, sub)` mapping)
- `GET /api/v1/admin/ping` → `{"status": "ok"}` for persisted owners
- unauthenticated → 401; authenticated non-owner → 403; owner → 200
- JWT `roles`, communications scopes, headers/body/query, and mailbox identity cannot grant owner
- no production promotion/bootstrap path

Out of scope (deferred):

- secure first-owner bootstrap / promotion (19D)
- `/me` + frontend owner awareness (19E)
- admin dashboard / user management APIs

## 19D — Secure first-owner bootstrap

**CLOSED / PASS.**

Implemented the operator-only first-owner promotion mechanism. **Real owner activation was not performed.**

### Bootstrap design

```text
python -m app.cli.promote_owner --user-id <existing-users.id-uuid>
```

- Requires `DATABASE_URL`
- Targets an **existing** internal `users.id` only
- Requires an External ID mapping on that user
- Conditionally updates `application_role` from `user` → `owner`
- First-owner invariant: fails closed if a different owner already exists
- Idempotent when the same user is already `owner`
- Never creates users
- No public HTTP role-write API
- No email / JWT / mailbox selectors

### Why `--user-id`

Passing the opaque internal UUID avoids placing durable External ID `(iss, sub)` values into shell history. Operators verify External ID sign-in separately, then resolve `users.id` from `external_identities` outside this command before invoking it.

### Security assumptions

- Ordinary signup / `resolve_or_create` still creates only `user`
- Owner authorization remains server-side DB role checks (19C)
- Bootstrap is an offline/operator process, not an application request path
- Tracked docs/source never contain real owner identity values

### Later real activation (NOT executed in 19D)

1. Ensure the environment database is migrated to Alembic head including `19b0001`
2. Designated human signs in once via ordinary External ID product login
3. Operator resolves that person's internal `users.id` from `external_identities` for the verified `(iss, sub)` (outside git/docs)
4. Operator runs `python -m app.cli.promote_owner --user-id <uuid>` with `DATABASE_URL` for that environment
5. Confirm with an authenticated owner call to `GET /api/v1/admin/ping`

## 19E — `/me` + frontend owner awareness

**CLOSED / PASS.**

Implemented server-authoritative current-user identity and minimal frontend owner presentation. **Real owner activation has still NOT occurred.** Phase 19D bootstrap exists but has not been executed against a real owner account.

### Delivered

- `GET /api/v1/me` → `{ "application_role": "user"|"owner", "is_owner": bool }`
- Auth via verified JWT → `(iss, sub)` → existing `external_identities` mapping → persisted `users.application_role`
- Does **not** create users; missing mapping → 404
- Omits `user_id`, issuer, subject, email, mailbox identity, and tokens (SPA needs role only)
- Frontend `CurrentUserProvider` fetches `/me` for authenticated sessions only
- Minimal **Platform Owner** badge in the signed-in shell when `is_owner` is true from `/me`
- Owner UI is presentation only; `require_owner` remains the security boundary
- Communications `PermissionGate` / `communications:*` scopes remain separate from `application_role`
- No admin dashboard, role-management APIs, Entra changes, or real promotion

### Security assumptions

- Frontend role state never authorizes `GET /api/v1/admin/ping` or other owner routes
- JWT `roles`, scopes, email, and mailbox identity cannot change `/me` or grant owner
- `/me` failure never yields owner UI
- Logout / account-key change clears owner presentation state

## 19F — Security regression matrix + documentation closure

Not started.

Intended scope:

- offline security regression covering non-owner denial, create-path non-promotion, mailbox/email non-grant, and server-authoritative `/me`
- Phase 19 documentation closure
- preserve Phase 18 CLOSED / PASS

## Non-goals (initial Phase 19)

- admin dashboard product UI
- workforce-Entra → External-ID federation
- treating Entra JWT `roles` as application RBAC
- mailbox-login / application-login merging
- organizations / teams / SaaS tenancy
- changing Foundry, Bedrock, Azure RBAC, or AWS IAM into application role sources
- embedding real owner identity values in the repository

## Prerequisites for later slices

From the readiness assessment:

- Phase 18 CLOSED / PASS
- External ID product login and `(iss, sub)` mapping remain the identity foundation
- persistence and Alembic tooling available for the role column
- operator availability to promote a real owner identity per environment using the 19D CLI, outside tracked source

## Related documents

- [ADR-028](../decisions/ADR-028-platform-owner-identity-and-application-rbac.md)
- [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-027](../decisions/ADR-027-microsoft-entra-external-id-customer-authentication.md)
- [Phase 18](phase-18-secure-attachment-intelligence.md) — CLOSED / PASS
- [Roadmap index](README.md)
