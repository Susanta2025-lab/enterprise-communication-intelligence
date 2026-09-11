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
| **19F** Security regression matrix + documentation closure | **CLOSED / PASS** |
| Phase 19 overall | **CLOSED / PASS** |

Phase 18 remains **CLOSED / PASS**. Phases 19A–19F remain **CLOSED / PASS**. Phase 19 overall is **CLOSED / PASS**. Do not reopen or rewrite completed phases.

**Important:** the controlled first-owner bootstrap command exists, but **real owner activation has NOT occurred**. No real `(iss, sub)` values were captured or stored in the repository. Operators must run promotion later against an environment database after ordinary External ID sign-in.

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

**CLOSED / PASS.**

Completed the Phase 19 security/regression review and documentation closure against ADR-028 and the implemented 19B–19E code. **Real owner activation was NOT performed.** No live Azure/AWS mutation, Entra change, or `promote_owner` against a real environment occurred in this slice.

### IMPLEMENTED (technical capability)

- constrained `users.application_role` (`user` \| `owner`, default `user`)
- server-side `require_owner` and minimal `GET /api/v1/admin/ping`
- operator-only first-owner bootstrap CLI
- server-authoritative `GET /api/v1/me` (`application_role`, `is_owner` only)
- frontend owner awareness (presentation only)
- offline security regression coverage for the Phase 19 matrix

### NOT PERFORMED

- real platform-owner activation / promotion in any environment
- workforce → External ID federation
- admin dashboard or generalized multi-role administration
- external business-user validation (Phase 17D remains deferred)

### Security regression matrix (evidence)

| # | Property | Evidence |
|---|---|---|
| 1 | ordinary user remains user | `test_me_endpoint`, identity repository create path |
| 2 | persisted owner recognized as owner | `test_admin_owner_authorization`, `test_me_endpoint` |
| 3 | normal signup cannot create owner | identity repository + migration defaults |
| 4 | `resolve_or_create` cannot promote | `test_identity_resolver`, owner bootstrap unit |
| 5 | email equality cannot grant owner | same-email/different-`sub` admin denial |
| 6 | different subject cannot impersonate owner | verified `(iss, sub)` resolution tests |
| 7 | JWT `roles=["owner"]` cannot grant owner | admin + `/me` JWT role denial |
| 8 | all `communications:*` scopes cannot grant owner | admin scope denial |
| 9 | frontend/client role state cannot grant owner | `/me` + frontend current-user tests |
| 10 | request header/query/body cannot grant owner | admin + `/me` client-claim denial |
| 11 | Gmail mailbox identity cannot grant owner | admin/me/bootstrap mailbox denial |
| 12 | Graph mailbox identity cannot grant owner | admin + `/me` Graph connector denial |
| 13 | unauthenticated admin → 401 | `test_admin_ping_without_token_returns_401` |
| 14 | normal authenticated user admin → 403 | `test_admin_ping_ordinary_user_returns_403` |
| 15 | persisted owner admin → 200 | `test_admin_ping_persisted_owner_returns_200` |
| 16 | unknown/corrupt role fails closed | admin 403 / `/me` 503 / DB check |
| 17 | persistence failure fails safely | admin + `/me` 503 on `PersistenceError` |
| 18 | bootstrap cannot create a user | owner bootstrap unit |
| 19 | nonexistent bootstrap target fails closed | owner bootstrap unit |
| 20 | failed bootstrap leaves DB unchanged | bootstrap failure/rollback cases |
| 21 | second distinct owner is rejected | first-owner invariant |
| 22 | repeated same-owner bootstrap is safe | idempotent `ALREADY_OWNER` |
| 23 | no HTTP application-role mutation exists | admin/bootstrap/me method denial |
| 24 | ordinary user cannot self-promote | bootstrap integration |
| 25 | `/me` reflects DB role, not token/client | `/me` claim-independence tests |
| 26 | `/me` does not expose sensitive identity fields | runtime + OpenAPI privacy assertions |
| 27 | logout clears frontend owner state | current-user shell badge clear |
| 28 | account/session switch cannot retain owner state | account-key switch test |
| 29 | `PermissionGate` independent from owner state | current-user PermissionGate test |
| 30 | cross-user resource isolation unchanged | owner probe + pre-existing ownership suites |

### OpenAPI / privacy

- Broad OpenAPI assertion `user_id` not present in the schema remains intact.
- `/me` schema exposes only `application_role` and `is_owner`.
- `/me` OpenAPI wording must not emit the internal identifier name (`user_id`).

### Real owner activation boundary

Technical owner/RBAC capability is complete. Secure operator bootstrap exists (`python -m app.cli.promote_owner --user-id <uuid>`). Real activation remains a separate operator action per environment after ordinary External ID sign-in and controlled resolution to internal `users.id`. Real `(iss, sub)` values must not be committed to source or docs.

### Multi-cloud

Application RBAC remains host-neutral:

```text
External ID → ECI API → PostgreSQL application_role
```

Identical on Azure-hosted and AWS-hosted ECI. Azure RBAC / AWS IAM are not application-owner truth. No Foundry/Bedrock changes were required for Phase 19.

## Non-goals (initial Phase 19)

- admin dashboard product UI
- workforce-Entra → External-ID federation
- treating Entra JWT `roles` as application RBAC
- mailbox-login / application-login merging
- organizations / teams / SaaS tenancy
- changing Foundry, Bedrock, Azure RBAC, or AWS IAM into application role sources
- embedding real owner identity values in the repository

## Prerequisites for real owner activation (operator)

From the readiness assessment and Phase 19 delivery:

- Phase 18 CLOSED / PASS
- External ID product login and `(iss, sub)` mapping remain the identity foundation
- persistence and Alembic tooling available for the role column (head includes `19b0001`)
- operator availability to promote a real owner identity per environment using the 19D CLI, outside tracked source

## Related documents

- [ADR-028](../decisions/ADR-028-platform-owner-identity-and-application-rbac.md)
- [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-027](../decisions/ADR-027-microsoft-entra-external-id-customer-authentication.md)
- [Phase 18](phase-18-secure-attachment-intelligence.md) — CLOSED / PASS
- [Roadmap index](README.md)
