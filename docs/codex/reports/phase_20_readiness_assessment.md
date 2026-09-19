# Phase 20 — Business Context & Matter Intelligence
# Readiness and Architecture Assessment

**Document type:** Assessment only (no implementation)
**Date:** 2026-09-18
**Branch inspected:** `master`
**HEAD:** `ed5eebc24303b7697dc90e4f79cf9b87361ed1b9`
**Alembic head verified:** `19b0001`
**Verdict:** **READY WITH CONDITIONS**

**Phase 20A follow-up:** Conditions in §38 were resolved by architecture lock [ADR-029](../../decisions/ADR-029-business-context-foundation-and-provenance-association.md) and [Phase 20 roadmap](../../roadmap/phase-20-business-context-matter-intelligence.md). This assessment remains the pre-implementation evidence record and is not a claim that Phase 20 implementation is complete.

This document does **not** implement Phase 20. It does not modify application source, create SQLAlchemy models or Alembic migrations, change frontend routes, mutate cloud resources, connect mailboxes, retrieve attachments, or invoke AI providers.

Repository convention note: prior phase readiness assessments lived inside `docs/roadmap/phase-NN-*.md`. Creating a Phase 20 roadmap file now would incorrectly signal that implementation has begun. This assessment is therefore filed at `docs/codex/reports/phase_20_readiness_assessment.md` until the Solution Architect authorizes a Phase 20 roadmap document.

---

## 1. Executive assessment

Phase 19 closed cleanly. The repository has a coherent, cloud-neutral stack for identity mapping, user-owned persistence, mailbox isolation, fail-closed attachment intelligence, and approval-gated workflow execution. That stack is a solid foundation for a durable **BusinessContext** abstraction.

The decisive architectural constraint is not missing RBAC or attachment security—it is that **mailbox communications are not durable rows**. There is no `communications` table. Durable product records today are:

| Durable object | Table |
|---|---|
| User / identity map | `users`, `external_identities` |
| Communication analysis | `analyses` |
| Connector account | `connector_accounts` |
| Mailbox OAuth session | `mailbox_authorization_sessions` |
| Workflow action | `workflow_actions` |
| Attachment analysis | `attachment_analyses` |

A “communication associated with a matter” must therefore be modeled as an **owned provenance association** (for example `(connector_account_id, provider_message_id)` and/or links to durable `analyses` / `attachment_analyses` / `workflow_actions`), never as a foreign key to a non-existent communication entity, and never by fetching mailbox or attachment bytes as a side effect of association.

Platform Owner (`application_role=owner`) is **platform administration**, not object ownership. It does not bypass `users.id` isolation today and must not be used as a shortcut for shared matters.

**Recommended first slice:** `20A` — Architecture / ADR lock only (no schema yet), freezing ownership, association, cascade, and non-goals before any migration.

---

## 2. Repository baseline verified

| Check | Result |
|---|---|
| Current branch | `master` |
| Working tree (pre-report) | Clean |
| HEAD | `ed5eebc` — `docs: normalize Phase 18 and 19 completion status` |
| Roadmap Phases 1–16 | Completed |
| Phase 17A–17C | CLOSED / PASS |
| Phase 17D | Deferred / out of current release scope |
| Phase 18 | CLOSED / PASS |
| Phase 19 | CLOSED / PASS (19A–19F) |
| Alembic heads | Single head `19b0001` |
| Expected schema head | `19b0001` — **matches** |
| Phase 20 roadmap / code | **Absent** (expected) |

### Alembic chain (verified)

```text
9a0001 → 10b0001 → 11b0001 → 12a0001 → 13a0001 → 16f0001 → 18d0001 → 19b0001
```

Phases 14/15/17 intentionally shipped no schema revisions.

### Documentation vs implementation discrepancies

| Item | Status |
|---|---|
| Phase 18/19 CLOSED/PASS in roadmap README vs code | Aligned |
| Phase 18 roadmap still mentions historical Alembic head `18d0001` in places | Stale relative to current head `19b0001`; Phase 19/README are correct |
| `docs/api/endpoints.md` “as of Phase 16F-A2” framing | Partially stale; Phase 18/19 routes exist in code (`attachment-analyses`, `/me`, `/admin/ping`) |
| Phase 20 product sequence in this assessment | Not yet in `docs/roadmap/README.md` (correct until implementation is authorized) |

**No blocking baseline deviation from the expected Phase 19 head.**

---

## 3. Current architecture relevant to Phase 20

Dependency direction (enforced in practice):

```text
API → Application → Domain → Interfaces → Providers / Infrastructure
```

Relevant layers for BusinessContext:

- **API:** FastAPI routers under `/api/v1`; auth via `authenticate_caller` / `require_permission` / `require_owner`.
- **Application:** orchestration services (`connected_mailbox_*`, workflow, attachment analysis, identity).
- **Domain:** provider-neutral models and ports; no FastAPI / Azure / AWS imports.
- **Infrastructure:** SQLAlchemy models, repositories, connectors, scanners, credential stores.

Existing ownership pattern for every durable user resource:

```text
verified (iss, sub) → users.id → row.user_id equality in SQL → 404 if miss
```

Capability permissions (`communications:*`) gate endpoints; they do **not** replace object ownership.

---

## 4. Existing identity and RBAC model

### Identity separation (enforced)

```text
ECI APPLICATION LOGIN  ≠  MAILBOX LOGIN
≠  CLOUD WORKLOAD IDENTITY
≠  DATABASE IDENTITY
≠  DEPLOYMENT IDENTITY
```

Evidence:

- `AuthenticatedPrincipal` carries `issuer`, `subject`, `permissions` only (`app/core/security.py`). Email is not used for auth.
- Mapping key is unique `(issuer, subject)` on `external_identities` (ADR-013, ADR-027, ADR-028).
- `users` has **no PII/email columns**.
- Mailbox OAuth credentials live in Key Vault / Secrets Manager via opaque `credential_ref`.
- Platform Owner: `require_owner` loads `users.application_role` after `(iss, sub)` resolution (`app/api/dependencies.py`). JWT `roles`, scopes, email, and mailbox identity are ignored.
- First owner bootstrap: CLI `python -m app.cli.promote_owner --user-id <uuid>` only; no public role-write API.
- `GET /api/v1/me` returns `{application_role, is_owner}` for UX; documented as non-authoritative for security.
- Frontend Platform Owner badge is presentation-only.

### Application roles today

| Role | Meaning |
|---|---|
| `user` | Ordinary application user (default; all signups) |
| `owner` | Platform Owner — currently gates `GET /api/v1/admin/ping` only |

**Critical for Phase 20:** `owner` does **not** mean “owner of BusinessContext data,” and does **not** bypass object-level `user_id` checks. Cross-user admin access would require a new explicit ADR (ADR-028 already warns against silent widening).

---

## 5. Existing ownership model

| Aggregate | Ownership column | Lookup pattern |
|---|---|---|
| Analyses | `user_id` | `get_by_id_for_user` / `list_for_user` |
| Connector accounts | `user_id` | `get_owned` / `list_owned` |
| Workflow actions | ORM `user_id` (domain `owner_user_id`) | `get_owned` / `list_owned` / `save_owned` |
| Attachment analyses | `user_id` | `get_by_id_for_user` / `list_for_user` |
| Mailbox auth sessions | `user_id` | owned session APIs |

Conventions to preserve:

- SQL always includes `user_id`.
- Unknown id and cross-user id are indistinguishable → HTTP **404**.
- List pagination: newest first (`created_at DESC, id DESC`), `limit` 1–100 (default 20).
- IDs: `uuid4` + SQLAlchemy `Uuid`.
- Statuses: Python `StrEnum` + DB `Text` + `CheckConstraint` (not PostgreSQL ENUM types).
- No soft-delete / `archived_at` pattern exists yet; disconnect uses status mutation; analysis delete is hard delete.

---

## 6. Existing mailbox isolation model

Authoritative gate: `load_owned_connector_account` + `is_usable_for_mailbox_read` (`app/application/services/connected_mailbox_access.py`).

Rules:

1. Resolve caller to `users.id` via `(iss, sub)` (`find_existing`; no mapping ⇒ treat as not found).
2. Load connector with `connector_account_id` **and** `user_id`.
3. Require `ACTIVE`, routable provider, `mail.read` capability, non-empty `credential_ref` before mailbox I/O.
4. Credentials never resolve before ownership + usability succeed.

**Authoritative Phase 20 association rule (derived from current code):**

```text
authenticated application user
  == business_context.user_id
  == connector_account.user_id
  == (when linking durable analyses / attachment_analyses / workflows) that row's user_id
```

Do **not** infer association rights from:

- email address
- Gmail / Outlook mailbox address
- sender / recipient fields
- mailbox OAuth identity
- Platform Owner role

User A must never associate or read User B’s mailbox message through a context ID. Association create/delete must re-validate ownership of both the context and the target provenance on every mutation.

---

## 7. Existing attachment-security model

Phase 18 contract (must remain intact):

```text
Attachment listing does NOT retrieve attachment bytes.
Attachment content is retrieved only after explicit Analyze for one specific attachment.
Exactly one requested attachment is retrieved.
Security policy executes before parsing/AI.
ClamAV executes before parser/AI.
Unsupported formats fail closed.
Raw attachment bytes do not become durable product storage.
Attachment analysis cannot trigger Propose / Approve / Execute / Send.
```

Evidence points:

- Metadata list vs explicit analyze routes under mailbox attachments.
- Default scanner `none` → unavailable / fail-closed in production.
- `attachment_analyses` stores structured results only (no bytes / extracted text / prompts).
- `workflow_actions.analysis_id` is intentionally **not** an FK to `attachment_analyses`.

**Phase 20 implication:** “Add to context” / “Open context” must not download attachments. Context associations reference durable metadata/identifiers (`attachment_analyses.id` and/or `(connector_account_id, provider_message_id, provider_attachment_id)`), not raw content.

---

## 8. Existing workflow model

State machine (`app/domain/models/workflow.py`):

```text
PENDING → APPROVED | REJECTED
APPROVED → EXECUTING
EXECUTING → EXECUTED | FAILED
```

Authorization:

| Action | Permission | Ownership |
|---|---|---|
| Propose | `communications:workflow` | Owned analysis snapshot |
| Approve / Reject | `communications:workflow` | Owned PENDING action |
| Execute / Send | `communications:send` | Owned APPROVED → EXECUTING before provider I/O |
| Get / List | `communications:workflow` | Owned only |

AI analysis and attachment analysis never auto-send. BusinessContext association must not grant approve/execute rights and must not change the state machine.

---

## 9. Existing persistence / Alembic architecture

- Linear Alembic; portable PostgreSQL (Azure Flexible Server and AWS RDS independently).
- FK `ON DELETE CASCADE` only for true dependents of `users.id` (and short-lived mailbox sessions → connector).
- Provenance UUIDs without FK when history must survive parent lifecycle (`analyses.connector_account_id`, `workflow_actions.analysis_id` / `connector_account_id`, `attachment_analyses.connector_account_id`).
- JSON via portable `JSON`/`JSONB` variant.
- Forbidden speculative tenancy tables are actively tested against (`tenants`, `organizations`, `memberships`, etc.).

Phase 20 migrations must continue this portable, additive style and apply independently on Azure and AWS databases (no cross-cloud replication).

---

## 10. Frontend architecture

| Concern | Current state |
|---|---|
| Stack | React + TypeScript + Vite SPA |
| Auth | MSAL / External ID; bearer via `EciApiClient` |
| Data | TanStack Query hooks |
| Routes | `/` dashboard; `/mailbox/:connectorAccountId` workspace |
| Owner UX | Badge from `/me` only |
| Permissions UX | Token scopes for gating controls; server remains authority |

No contexts / matters UI exists. Phase 20 should add a minimal parallel route tree without redesigning mailbox or connector flows.

---

## 11. BusinessContext domain options

### Option A — Flat user-owned BusinessContext (recommended baseline)

Generic durable container with constrained `type` and archive lifecycle. Associations are separate tables. No hierarchy, no sharing, no vendor fields.

**Pros:** Matches ADR-013 user ownership; smallest schema; cloud-neutral; easy Phase 21–23 FKs.
**Cons:** Client→Matter nesting deferred; multi-context labeling requires M2M (acceptable).

### Option B — Hierarchical contexts from day one (`parent_context_id`)

**Pros:** Models Client→Matter early.
**Cons:** Cycle checks, recursive auth, list/filter complexity; unnecessary for MVP timeline UX.

### Option C — Separate Client entity + Matter entity

**Pros:** Strong legal-matter fit.
**Cons:** Premature domain specialization; fights “platform-neutral naming”; harder for project/transaction users.

### Option D — Org/tenant shared contexts

**Pros:** Collaboration.
**Cons:** Explicitly out of scope; contradicts current forbidden tenancy posture and Phase 19 owner semantics.

---

## 12. Recommended BusinessContext model

### Entity: `BusinessContext`

| Field | Recommendation | Rationale |
|---|---|---|
| `id` | `Uuid` PK, `uuid4` | Existing convention |
| `user_id` | FK → `users.id` `ON DELETE CASCADE` | Server-authoritative ownership (ORM name matches repo; domain may expose `owner_user_id`) |
| `type` | Constrained text enum | Extensible product vocabulary without free-form chaos |
| `title` | Required text (length-bounded) | Primary display |
| `description` | Optional text (length-bounded) | Useful; minimize in logs |
| `reference` | Optional text | External/human case or project reference; **not** auth |
| `status` | `active` \| `archived` | Minimal lifecycle |
| `created_at` / `updated_at` | Aware UTC | Existing convention |
| `archived_at` | Nullable timestamp | Archive with auditability; prefer over hard delete |
| `version` / optimistic lock | **Defer** | Workflow already has status CAS where needed; add later if concurrent edits appear |

### Recommended initial `type` values

```text
matter | case | project | client | transaction | account | other
```

Use `StrEnum` + `CheckConstraint`. Prefer allowing additive enum expansion via later migration over unconstrained free strings.

### Explicitly deferred / rejected for Phase 20 core row

- Vendor-specific fields (Clio matter id, Salesforce account id, SharePoint URL)
- `tenant_id` / org membership
- `parent_context_id` (see hierarchy decision)
- Hard delete API for contexts with associations (prefer archive)
- Email / mailbox address as owner key

---

## 13. Context hierarchy decision

**Recommendation: flat in Phase 20.**

- Do **not** add `parent_context_id` yet.
- Represent “Client” as either a `type=client` context or a free-text `reference` / title convention—not a second entity.
- Revisit hierarchy only when product UX proves Client→Matter navigation needs first-class nesting.
- If hierarchy returns later, require cycle prevention, same-owner parent/child, and explicit archive semantics for subtrees.

Smallest architecture that still supports later product direction: flat contexts + many-to-many associations + timeline read model.

---

## 14. Communication association design

### Reality check

There is **no durable communication row**. Association targets must be provenance-shaped.

### Recommended model: many-to-many via association table

`business_context_communications` (name illustrative):

| Column | Notes |
|---|---|
| `id` | uuid4 PK |
| `business_context_id` | FK → contexts; **RESTRICT or NO ACTION** on delete (prefer archive; refuse hard delete while linked) |
| `user_id` | Denormalized owner for cheap isolation checks; must equal context.user_id |
| `connector_account_id` | Owned connector UUID (application-validated; optional FK — see trade-off) |
| `provider_message_id` | Opaque provider message id |
| `analysis_id` | Optional link to durable `analyses.id` when available (no hard FK required) |
| `associated_by_user_id` | Same as owner in Phase 20 (manual only) |
| `associated_at` | Timestamp |
| `source` | `manual` (Phase 20); later `ai_confirmed` |
| Unique | `(business_context_id, connector_account_id, provider_message_id)` |

**Cardinality:** one communication provenance → **many** contexts (and one context → many communications). A single email can reasonably belong to multiple matters/projects.

### Authorization on associate

```text
1. Resolve caller → users.id
2. Load context WHERE id AND user_id
3. Load connector WHERE connector_account_id AND user_id
4. Optionally verify analysis_id / attachment links are same user_id
5. Insert association
```

Never fetch message body as part of association.

### Removal

Deleting an association removes only the link. It must not delete mailbox messages, analyses, attachment analyses, or workflows.

### Manual vs AI

Phase 20 foundation: `source=manual` only. AI suggestions are non-authoritative and belong in a later slice (20F).

---

## 15. Attachment association design

**Recommendation: hybrid — B primary for analyzed documents, A implicit for message-level.**

| Approach | Phase 20 stance |
|---|---|
| A. Indirect via parent communication association | Always available; listing “documents” can join attachment metadata **without** retrieving bytes |
| B. Direct context ↔ attachment association | Preferred for analyzed artifacts and Phase 21 XLSX findings |
| C. Both | Yes: communication association for thread context; optional `business_context_attachment_analyses` (or generic document link) for durable analysis rows |

Recommended durable direct link:

```text
business_context_id + attachment_analysis_id (+ user_id)
```

For not-yet-analyzed attachments, store metadata pointers only:

```text
(connector_account_id, provider_message_id, provider_attachment_id, filename, media_type)
```

and **never** auto-retrieve. Opening a context lists pointers; Analyze remains the existing Phase 18 endpoint.

Phase 21 XLSX then attaches findings to the existing `attachment_analyses` row already linked to the context.

---

## 16. Analysis association design

**Recommendation:** analyses remain source-owned; contexts query through association—not by copying analysis payloads.

| Analysis kind | Association |
|---|---|
| Communication `analyses` | Optional `analysis_id` on communication association **or** separate association table |
| `attachment_analyses` | Direct context ↔ attachment_analysis association |

Avoid duplicating summary/action_items into the context row. Timeline and workspace read models join existing tables.

---

## 17. Workflow association design

**Recommendation for Phase 20:**

- Prefer **inherit via communication provenance** and/or optional association table linking `workflow_actions.id` → `business_context_id`.
- Do **not** put a required `business_context_id` on `workflow_actions` (would break optional-context backwards compatibility).
- Do **not** let context membership authorize approve/execute.
- If association changes after approval, keep workflow provenance immutable; association is organizational metadata, not execution authority.
- Multi-context workflow links: allow many-to-many if needed; default UX can show workflows whose `connector_account_id` + `provider_message_id` match associated communications.

Phase 20 must not change approval/execution semantics.

---

## 18. Ownership and authorization model

### Principles

```text
BusinessContext ownership is server-authoritative.
owner_user ≡ users.id from (iss, sub)
Email / mailbox identity never grants context rights.
application_role=owner does not bypass object ownership in Phase 20.
Shared / multi-user contexts are explicitly out of scope.
```

### Permissions (proposed)

Reuse existing capability model; avoid inventing a large new scope matrix unless ADR requires it.

Pragmatic Phase 20 approach:

| Operation | Suggested gate |
|---|---|
| CRUD / archive contexts | Authenticated mapped user + object ownership; permission `communications:analyze` **or** a new `communications:context` if architect prefers separation |
| Associate mailbox provenance | Ownership of context + connector; likely also `communications:read` |
| Timeline / workspace read | Ownership + same capability as list |

**Architect decision required (Condition):** whether contexts reuse `communications:analyze` / `read` or introduce a dedicated scope. Default recommendation: **reuse `communications:analyze` for context CRUD** and **`communications:read` for association that touches mailbox identifiers**, to avoid Entra app-registration churn before product need is proven. Document the choice in 20A ADR.

### Object checks

- Create: bind `user_id` from resolver only (ignore client-supplied owner).
- Read/Update/Archive: `id + user_id`; miss → 404.
- Associate: both sides owned; miss → 404.
- Enumeration protection: no existence oracle via 403.

---

## 19. Context lifecycle / archive model

| State | Semantics |
|---|---|
| `active` | Default; editable; associable |
| `archived` | Hidden from default lists; read-only associations; restore optional |

Semantics:

- **Create:** active context for caller.
- **Update:** title/description/reference/type (type mutation: allow with care; prefer limited).
- **Archive:** set `status=archived`, `archived_at=now`; do not delete associations; do not touch mailbox providers.
- **Restore:** clear archive fields (if exposed).
- **Hard delete:** out of Phase 20 API surface. If ever added, refuse while associations exist or null associations first; never CASCADE-delete analyses/workflows/attachment_analyses/mailbox data.
- **Retention:** follow existing user-cascade only when the **user** row is deleted.

Archiving a context must not delete Gmail/Outlook messages or destroy unrelated durable records.

---

## 20. Timeline / read-model design

Desired UX (Matter timeline) can be satisfied without a duplicated event store initially.

**Recommendation: hybrid.**

| Layer | Role |
|---|---|
| Authoritative sources | Associations + existing `analyses`, `attachment_analyses`, `workflow_actions` timestamps/status |
| Read model | Application query assembling typed timeline items |
| Optional later | `business_context_events` only if audit/external integrations need append-only facts not reconstructible from sources |

Phase 20 first implementation: **query/read model (B)** with stable synthetic item ids such as `analysis:<uuid>`, `attachment_analysis:<uuid>`, `workflow:<uuid>:<status_ts>`, `association:<uuid>`.

Concerns:

- Order by event timestamp DESC, then stable id.
- Paginate with `limit`/`offset` or keyset on `(event_at, item_id)`.
- Cap page size (≤100).
- Do not pull attachment bytes or message bodies to build timeline.
- Future work items / XLSX findings / external sync events can register new item types without rewriting contexts.

---

## 21. API architecture

Align with existing `/api/v1` routers, Pydantic v2 schemas, OpenAPI `ErrorResponse`, and 404-indistinguishability.

### Proposed routes (illustrative; finalize in 20A)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/contexts` | Create |
| `GET` | `/api/v1/contexts` | List owned (`status`, `type`, `q` optional) |
| `GET` | `/api/v1/contexts/{context_id}` | Get one |
| `PATCH` | `/api/v1/contexts/{context_id}` | Update mutable fields |
| `POST` | `/api/v1/contexts/{context_id}/archive` | Archive (idempotent if already archived) |
| `POST` | `/api/v1/contexts/{context_id}/restore` | Optional restore |
| `GET` | `/api/v1/contexts/{context_id}/timeline` | Paginated read model |
| `POST` | `/api/v1/contexts/{context_id}/communications` | Associate provenance |
| `DELETE` | `/api/v1/contexts/{context_id}/communications/{association_id}` | Remove association |
| `POST` | `/api/v1/contexts/{context_id}/attachment-analyses/{id}` | Associate durable attachment analysis |
| `DELETE` | `/api/v1/contexts/{context_id}/attachment-analyses/{id}` | Remove link |

Prefer association ids in DELETE paths over raw provider message ids in URLs (provider ids can be awkward / leaky in logs).

### Per-endpoint contract sketch

**Common:** Bearer auth; resolve `(iss,sub)` → `users.id`; ownership on every mutation; never trust client `user_id`.

| Endpoint | AuthZ | Request | Response | Errors |
|---|---|---|---|---|
| Create | mapped user + capability | type, title, description?, reference? | context | 401/403/422/503 |
| List | mapped user | limit/offset + filters | page | 401/403/503; empty if unmapped |
| Get | owned | — | context | 404 cross-user |
| Patch | owned + active (or allow archived metadata policy) | partial fields | context | 404/409 if archived policy forbids |
| Archive | owned | — | context | 404; 200 idempotent |
| Timeline | owned | limit/offset | items | 404 |
| Associate communication | owned context + owned connector | connector_account_id, provider_message_id, analysis_id? | association | 404/409 duplicate |
| Disassociate | owned | — | 204 | 404 |

Idempotency: duplicate association → `409` with stable message **or** idempotent `200` returning existing row; pick one in ADR (prefer **409** for explicit UX, or idempotent PUT-style for simpler clients).

**Do not** add endpoints that retrieve attachment bytes under `/contexts/...`.

---

## 22. Frontend architecture proposal

Minimal Phase 20 UX:

```text
/contexts                     → list + create
/contexts/:contextId          → workspace
   Overview | Communications | Documents | Analyses | Workflow history
```

Implementation notes:

- Add routes beside existing dashboard/mailbox; do not redesign connector OAuth UX.
- TanStack Query keys: `['contexts']`, `['contexts', id]`, `['contexts', id, 'timeline']`, association mutations invalidate timeline + lists.
- Auth: same MSAL/`EciApiClient`; clear context queries on logout.
- Loading/error: reuse `ProductErrorState` / 404 mapping (treat cross-user as not found).
- Pagination: mirror analyses list patterns.
- Manual association UX: from mailbox selected message → “Add to context” picker; and from context workspace → search owned recent analyses / enter message from owned connector (keep UX small).
- Responsive: single-column workspace on narrow viewports.
- Defer Actions/Deadlines/Obligations/External systems sections (Phase 22–23); optional disabled nav placeholders only if Product insists—default **omit**.

---

## 23. AI-assisted association policy

```text
AI MAY SUGGEST.
AI MUST NOT silently assign an email, attachment, workflow, task, deadline, or obligation to an authoritative BusinessContext.
```

### Phase 20 stance

- **20A–20E:** manual authoritative association only.
- **20F (optional later slice):** non-authoritative suggestions.

### Future suggestion architecture (design only)

```text
Existing communication analysis
→ candidate contexts (same user_id only)
→ AI suggestion
→ ContextSuggestion (non-authoritative)
→ human confirm
→ authoritative association (source=ai_confirmed)
```

If persisted:

- `context_suggestions` with confidence, status (`pending`/`accepted`/`dismissed`/`expired`), created_at, expires_at.
- Candidate selection limited to caller-owned contexts.
- Prompts must not include other users’ titles/descriptions/messages.
- Stale suggestions invalidated when context archived or association already exists.
- Acceptance creates association via the same ownership-validated service path as manual associate.

Privacy: do not log suggestion prompt bodies or full message text.

---

## 24. Phase 21 XLSX compatibility

Phase 20 decisions that keep Phase 21 easy:

- Direct link from context → `attachment_analyses` (structured results).
- Timeline item type ready for `attachment_analysis` / future `xlsx_finding`.
- No assumption that all attachments are PDF/DOCX in association schema (`kind` stays on analysis row).
- No auto-retrieve-on-associate.

Avoid:

- Persisting raw XLSX bytes on the context.
- Coupling context schema to spreadsheet columns.
- Bypassing ClamAV/parser gates through context APIs.

---

## 25. Phase 22 work-item compatibility

```text
WorkItem { action | deadline | obligation } → business_context_id + user_id
```

Phase 20 needs **no** generic extension framework. A future FK from `work_items.business_context_id` → `business_contexts.id` is sufficient. Avoid speculative plugin registries, Redis, or workers now.

---

## 26. Phase 23 external-integration compatibility

Future mapping table (not Phase 20):

```text
business_context_id + system + external_object_id + user_id
```

Phase 20 requirement: stable `BusinessContext.id` UUID only. **No** SharePoint/Clio/Salesforce columns on the core context row.

---

## 27. Database / migration strategy

### Starting head

```text
19b0001  →  20b0001 (illustrative; final id set when 20B ships)
```

### Proposed tables (conceptual)

1. **`business_contexts`**
   - columns per §12
   - FK `user_id → users.id ON DELETE CASCADE`
   - indexes: `(user_id, created_at, id)`, `(user_id, status, updated_at)`, optional `(user_id, type)`, optional `(user_id, reference)` where reference not null
   - checks: type enum; status `active|archived`; archived_at null iff active (or allow null always with status authoritative)

2. **`business_context_communication_links`**
   - columns per §14
   - UNIQUE `(business_context_id, connector_account_id, provider_message_id)`
   - FK context: `ON DELETE RESTRICT` (force archive-not-delete) **or** `CASCADE` only if product chooses hard-delete-with-links-only (prefer RESTRICT + no hard delete API)
   - **Do not** FK-cascade to analyses/workflows
   - Validate connector ownership in application; optional non-FK provenance (consistent with analyses) **or** FK to `connector_accounts` with `ON DELETE RESTRICT`

3. **`business_context_attachment_analysis_links`**
   - UNIQUE `(business_context_id, attachment_analysis_id)`
   - application validates same `user_id`
   - prefer **no FK CASCADE** from attachment_analyses deletion automatically wiping audit of “was linked”—or CASCADE link row only (not the analysis). Prefer: link FK to attachment_analyses `ON DELETE CASCADE` (link disappears if history deleted) and to context `ON DELETE RESTRICT`.

### Sequencing

1. Add `business_contexts`.
2. Add association tables.
3. No backfill required for empty production data.
4. Apply independently on Azure PG and AWS RDS after app revision that understands the schema (expand/contract: deploy code that tolerates absence only if using feature flags—prefer migrate-then-deploy per existing cloud practice).

### Rollback

- Downgrade drops association tables then contexts.
- Safe when no critical prod dependence yet; after data exists, prefer forward fix.
- Never cascade-delete `analyses` / `attachment_analyses` / `workflow_actions` from context teardown.

### PostgreSQL compatibility

Stay with portable types already used (`Uuid`, `Text`, `DateTime(timezone=True)`, JSON variant). No PG-only ENUMs, no extensions.

---

## 28. Index / query / performance strategy

| Query | Index support |
|---|---|
| List contexts for user | `(user_id, created_at, id)` + filter status |
| Open context | PK + user_id predicate |
| List links by context | `(business_context_id, associated_at, id)` |
| Find link by message | unique business key; also `(user_id, connector_account_id, provider_message_id)` |
| Timeline assembly | fetch bounded pages per source type; merge-sort in application **or** SQL `UNION ALL` with limit |

N+1 risks:

- Timeline hydrating each item with separate queries → use IN-clauses per type per page.
- Workspace “documents” listing triggering attachment retrieve → **forbidden**; metadata only.

Do not introduce Elasticsearch/OpenSearch/vector DB in Phase 20.

---

## 29. Threat model

| Threat | Expected control |
|---|---|
| IDOR / context enumeration | `user_id` predicate; 404 indistinguishability |
| Cross-user association | Validate context + connector + analysis ownership every time |
| Foreign mailbox message link | Owned `connector_account_id` required; no trust of client-only message ids without connector ownership |
| Attachment bytes via context | No retrieve endpoints under contexts; reuse Phase 18 analyze only |
| Unauthorized archive/update | Owned mutate only |
| Owner-role confusion | `application_role=owner` does not expand context access in Phase 20 |
| Mailbox/application identity confusion | Keep ADR-021/027/028 separations |
| Indirect attachment retrieval | Association stores ids/metadata only |
| AI cross-user leakage | Suggestions limited to same `user_id`; no cross-user candidate prompts |
| Malicious titles/descriptions | Length limits; encode in UI; never execute as code |
| Prompt injection via context fields | Treat context text as untrusted in any future AI suggest prompts |
| Excessive timeline queries | Hard page caps; authz before query |
| Association races | Unique constraint; transactional insert |
| Deletion/cascade mistakes | No CASCADE from context → analyses/workflows; prefer archive; RESTRICT hard delete |

---

## 30. Privacy assessment

BusinessContext adds sensitive business metadata (matter titles, client names, case references).

Controls:

- API: return only needed fields; no iss/sub/email on context resources.
- Logs: log `context_id`, `user_id` hashes/ids, operation names—**not** titles/descriptions/references by default (or hash/truncate if operationally required—prefer omit).
- Exceptions: generic details; no SQL/provider leakage.
- URLs: prefer association UUIDs over raw provider message ids where practical.
- Telemetry: counters/error_class only.
- Frontend cache: clear on logout; do not persist context titles in `localStorage`.
- AI prompts (future): minimize; same-user only; no other users’ contexts.

Preserve existing privacy-safe logging tests and extend them for context services.

---

## 31. Backwards-compatibility assessment

Business context must be an **optional enhancement**.

Unaffected without context:

- communication analyze
- attachment analyze
- workflow propose / approve / reject / execute
- connector OAuth
- `/me` and admin ping

No required schema changes to existing tables for MVP (association tables are additive). Avoid mandatory `business_context_id` on `analyses` or `workflow_actions`.

Existing API contracts remain; new routes are additive. Update OpenAPI/docs when implementing—not in this assessment.

---

## 32. Azure / AWS impact

| Topic | Assessment |
|---|---|
| Schema | Same Alembic revision on both DBs independently |
| App image | Same cloud-neutral domain/application code |
| Secrets / IAM | No new cloud identity for contexts |
| Replication | **None** |
| Deploy order | Migrate each environment’s PostgreSQL, then roll API/SPA |
| Provider SDKs | Domain/application must not import Azure/AWS SDKs for contexts |

No cloud mutations are part of this assessment.

---

## 33. Test strategy

### Domain

- Valid create; invalid type/status rejected.
- Archive/restore invariants.
- Ownership field always set from principal mapping.

### Persistence

- CRUD; unique association; FK/RESTRICT behavior; archive flags.
- Deleting context refused or non-cascading to analyses/workflows.
- User delete still cascades owned contexts (consistent with other user-owned rows).

### Authorization (minimum)

```text
User A cannot read / modify / archive User B context.
User A cannot associate User B communication / attachment analysis.
User A cannot access User B attachment bytes through context APIs (no such API).
application_role=owner does not bypass object ownership.
Mailbox identity cannot grant context ownership.
Email is not used in context authz paths (source scan / unit assert).
```

### API

- Auth 401/403; ownership 404; pagination bounds; conflict on duplicate association; idempotent archive.

### Attachment-security regression

- Context associate/list/timeline never call connector retrieve/scanner/parser.

### Workflow regression

- Context APIs never transition workflow state or call executors.

### Frontend

- List/create/workspace/archive/manual associate; unauthorized/error states; axe smoke as with Phase 15 patterns.

### Migration

- Upgrade from `19b0001`; downgrade if provided; empty DB; DB with existing users/mailboxes/workflows.

### Cloud neutrality

- Domain/application modules for contexts import neither Azure nor AWS SDKs (static/source tests).

---

## 34. Rollback strategy

| Stage | Rollback |
|---|---|
| 20A ADR only | Revert doc/ADR |
| 20B schema | Alembic downgrade before data reliance |
| 20C–20D API | Feature-flag or revert deploy; schema can remain empty-safe |
| 20E frontend | Revert SPA routes; API may remain unused |
| After production data | Prefer forward migrations; archive feature disable rather than destructive downgrade |

Never roll back by cascading deletes into mailbox-derived history tables.

---

## 35. Risks and blockers

| Risk | Severity | Mitigation |
|---|---|---|
| Mistaken assumption that communications are durable rows | High | Lock provenance association model in 20A |
| CASCADE design destroying analyses/workflows | High | RESTRICT + archive-only; tests |
| Using Platform Owner to share matters | High | Explicit non-goal; tests |
| Attachment retrieve shortcuts | High | No context retrieve APIs; regression suite |
| Scope/permission churn with Entra | Medium | Reuse existing scopes unless ADR says otherwise |
| Premature hierarchy / tenancy | Medium | Flat + single-user only |
| Stale API docs drift | Low | Update endpoints docs in implementation slices |
| Phase 17D deferred | Low | Not a technical blocker for Phase 20 engineering |

**No hard engineering blocker** prevents starting 20A.

---

## 36. Explicit non-goals (Phase 20)

Unless the Solution Architect explicitly expands scope:

- XLSX / XLSM parsing; image AI; OCR
- Autonomous mailbox ingestion / bulk analysis / background sync
- Autonomous context assignment
- Deadlines, reminders, obligations, calendar
- DMS / CRM / Clio / Salesforce / SharePoint sync
- Communication-risk / spam scoring
- New workers (Celery/Kafka/Redis/Kubernetes)
- New search platforms
- Cross-cloud DB replication
- Collaborative multi-user matters / org tenancy
- Live external-user testing (Phase 17D remains deferred)

---

## 37. Recommended Phase 20 implementation slices

Evaluated alternative: merge API+persistence earlier. Rejected—authz mistakes are costlier than an extra slice.

| Slice | Scope | Independently reviewable? |
|---|---|---|
| **20A** | Architecture / ADR lock (ownership, association provenance, cascade, scopes, non-goals) | Yes |
| **20B** | Domain model + SQLAlchemy + Alembic from `19b0001` + repository ownership tests | Yes |
| **20C** | Communication + attachment-analysis association services (manual only) | Yes |
| **20D** | HTTP API + OpenAPI + authz matrix | Yes |
| **20E** | Frontend list/workspace/timeline + manual associate UX | Yes |
| **20F** | AI suggestions only (non-authoritative) + confirm → associate | Yes (optional; can defer post-20G) |
| **20G** | Security hardening, regressions, docs, Azure/AWS migrate validation | Yes |

**Adjustment vs the prompt’s sketch:** rename association slice clearly around **provenance + attachment_analysis links** (not a fictional communications FK). Keep AI suggestions after a usable manual workspace exists.

---

## 38. Readiness verdict

```text
READY WITH CONDITIONS
```

### Conditions (must be satisfied in 20A before schema work)

1. **Association target model locked:** context links use owned `(connector_account_id, provider_message_id)` and/or durable analysis / attachment_analysis / workflow ids—not a `communications` table FK.
2. **Cascade policy locked:** archiving/deleting a context must not destroy analyses, attachment analyses, workflow history, or mailbox provider data.
3. **Platform Owner non-bypass locked:** `application_role=owner` does not grant cross-user context access in Phase 20.
4. **Shared contexts / hierarchy / external system fields** remain out of scope unless a new ADR explicitly opens them.
5. **Capability scope choice documented:** reuse existing `communications:*` permissions vs introduce `communications:context` (Entra registration impact acknowledged).
6. **Attachment invariant reaffirmed:** context features never retrieve attachment bytes.

### Recommended first implementation slice

```text
Recommended first implementation slice:
20A — Architecture / ADR lock

Why:
Freezes ownership, provenance association, cascade, and permission choices against the
verified absence of a durable communications table—preventing a wrong migration from
19b0001 and protecting Phase 18/19 invariants before any schema or API lands.
```

---

## Final verification (assessment task)

| Confirmation | Status |
|---|---|
| Non-mutating repository inspection performed | Yes |
| Production application code modified | **No** |
| SQLAlchemy models / Alembic migrations created | **No** |
| Frontend modified | **No** |
| Cloud resources mutated | **No** |
| Mailbox / attachment content accessed | **No** |
| Live AI providers invoked | **No** |
| Assessment document created | `docs/codex/reports/phase_20_readiness_assessment.md` |
| Phase 20 roadmap falsely marked in progress | **No** |

After this report is accepted, implementation may proceed under Solution Architect authorization starting at **20A**.
