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
| **19B** Role schema/model + safe migration | **Completed / PASS** |
| **19C** Server-side owner authorization | Not started |
| **19D** Secure first-owner bootstrap | Not started |
| **19E** `/me` + frontend owner awareness | Not started |
| **19F** Security regression matrix + documentation closure | Not started |
| Phase 19 overall | Next (19A–19B complete) |

Phase 18 remains **CLOSED / PASS**. Phase 19A remains **CLOSED / PASS**. Do not reopen or rewrite completed phases.

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
- Owner identity is captured and promoted only through a controlled operator step in a later slice (19D).
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

Not started.

Intended scope:

- server-side `require_owner` (or equivalent) guard
- fail closed for unauthenticated and non-owner callers
- keep `communications:*` permission checks separate
- minimal protected surface only as needed to prove the guard (no admin dashboard)

## 19D — Secure first-owner bootstrap

Not started.

Intended scope:

- controlled operator promotion path after ordinary External ID sign-in
- bind promotion to verified `(iss, sub)` / mapped `users.id`
- auditable one-shot (or equivalently controlled) bootstrap per environment
- never promote inside normal signup

Safety:

- do not commit real `(iss, sub)` values
- do not auto-promote from email allowlists
- do not use mailbox identities

## 19E — `/me` + frontend owner awareness

Not started.

Intended scope:

- server-authoritative `/me` (or equivalent) exposing application role from the database
- frontend reads role for visibility only
- no security enforcement in the SPA
- no admin dashboard

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
- operator availability to capture and promote a real owner identity only in 19D, outside tracked source

## Related documents

- [ADR-028](../decisions/ADR-028-platform-owner-identity-and-application-rbac.md)
- [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-027](../decisions/ADR-027-microsoft-entra-external-id-customer-authentication.md)
- [Phase 18](phase-18-secure-attachment-intelligence.md) — CLOSED / PASS
- [Roadmap index](README.md)
