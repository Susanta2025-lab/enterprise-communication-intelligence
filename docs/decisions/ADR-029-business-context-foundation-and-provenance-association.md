# ADR-029: Business Context Foundation and Provenance Association

## Status

Accepted

The Solution Architect locks this decision in Phase 20A. Implementation begins in Phase 20B and later slices. This ADR does **not** create SQLAlchemy models, Alembic migrations, FastAPI routes, frontend surfaces, AI suggestion flows, or cloud mutations.

This ADR does not rewrite [ADR-013](ADR-013-external-identity-mapping-and-user-owned-data.md), [ADR-015](ADR-015-approval-gated-workflow-actions.md), [ADR-016](ADR-016-workflow-persistence-and-analysis-provenance.md), [ADR-018](ADR-018-workflow-execution-target-provenance.md), [ADR-024](ADR-024-connected-mailbox-read-and-analysis-authorization-boundary.md), [ADR-027](ADR-027-microsoft-entra-external-id-customer-authentication.md), or [ADR-028](ADR-028-platform-owner-identity-and-application-rbac.md). It adds an optional, user-owned BusinessContext layer on top of those contracts.

Pre-implementation assessment: [Phase 20 readiness assessment](../codex/reports/phase_20_readiness_assessment.md) (`READY WITH CONDITIONS`). Phase 20A resolves those conditions.

## Date

Phase 20A (Business Context & Matter Intelligence — Architecture Lock)

## Context

Phases 1–19 deliver communication analysis, mailbox OAuth, approval-gated workflow execution, secure attachment intelligence, and application RBAC. Product direction requires a durable **business context** (matter / case / project / client / transaction / account) so users can organize communications and later attach XLSX intelligence, work items, and external system mappings.

Critical verified repository facts:

```text
There is NO durable communications table.
Mailbox messages are provider-backed.
Durable ECI records include analyses, attachment_analyses,
workflow_actions, and connector_accounts.
Alembic head at Phase 20A start: 19b0001
```

Identity separation remains absolute:

```text
ECI APPLICATION LOGIN
≠ MAILBOX LOGIN
≠ CLOUD WORKLOAD IDENTITY
≠ DATABASE IDENTITY
≠ DEPLOYMENT IDENTITY
```

Email is not an authorization key. Platform Owner (`users.application_role=owner`) is an administrative role and does not bypass object ownership (ADR-028).

## Decision

Introduce a flat, single-user-owned **BusinessContext** aggregate with **manual provenance associations** to provider-backed mailbox messages. Analyses, attachment analyses, and workflows appear in a context **read-model timeline** by derivation from those associations (and optional analysis provenance on the link). BusinessContext is optional: all existing mailbox, analysis, attachment, and workflow operations continue without a context.

Phase 20 does **not** implement hierarchy, shared contexts, AI-authoritative assignment, XLSX parsing, work items, or external DMS/CRM sync.

---

## BusinessContext v1 model

### Persistence table: `business_contexts`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Uuid` PK | no | Application-generated `uuid4` (same convention as other aggregates) |
| `user_id` | `Uuid` FK → `users.id` | no | Server-authoritative owner; `ON DELETE CASCADE` with user |
| `type` | `Text` | no | Check-constrained enum values (below) |
| `title` | `Text` | no | Required; trimmed; length 1–200 |
| `description` | `Text` | yes | Optional; trimmed; max 4000 when present |
| `reference` | `Text` | yes | Optional human/business reference; max 128; **not unique** |
| `status` | `Text` | no | `active` \| `archived`; check constraint |
| `archived_at` | `DateTime(timezone=True)` | yes | Set when archived; null when active |
| `created_at` | `DateTime(timezone=True)` | no | Aware UTC |
| `updated_at` | `DateTime(timezone=True)` | no | Aware UTC; bump on mutate |

### Domain naming

- Persistence / ORM / SQL: `user_id` (matches `analyses`, `connector_accounts`, `attachment_analyses`, `workflow_actions`).
- Domain entity may expose `owner_user_id` mapped to `user_id` (same pattern as domain `WorkflowAction.owner_user_id`), or use `user_id` consistently. Phase 20B must pick one mapping and keep it consistent; **authorization always uses internal `users.id`**.

### Ownership invariant

```text
business_contexts.user_id
  = authenticated ECI users.id
  = IdentityResolver mapping of verified (iss, sub)
```

Never derive ownership from email, mailbox account, sender, recipient, OAuth mailbox identity, display name, JWT roles, or client-supplied owner fields.

### `type` (v1)

Python `StrEnum` + DB `Text` + `CheckConstraint` (repository pattern; **not** PostgreSQL ENUM).

```text
matter | case | project | client | transaction | account | other
```

Extensibility: additive Alembic check-constraint migrations. Do not use unconstrained free-form type strings in v1.

### `title`

Required. Reject blank after trim. Max length **200**.

### `description`

**Included in v1 as optional.** Justified by Overview UX for matters/projects; not required for create. Max length **4000**. Omit from logs by default.

### `reference`

**Included in v1 as optional.** Examples: `MAT-2026-013`, `CASE-7712`. Max length **128**.

Uniqueness: **not enforced** (neither global nor per-user). Users may reuse labels. Optional non-unique index `(user_id, reference)` where `reference IS NOT NULL` may support filtering only.

### `status` / archive

Minimal lifecycle — **not** a multi-state machine:

```text
active ↔ archived
```

- `status='active'` ⇒ `archived_at IS NULL`
- `status='archived'` ⇒ `archived_at IS NOT NULL`
- Enforce with check constraint pairing status and `archived_at`.

No optimistic `version` column in v1.

### Indexes (proposed)

- PK on `id`
- `ix_business_contexts_user_id_created_at_id` `(user_id, created_at, id)` — default list
- `ix_business_contexts_user_id_status_updated_at` `(user_id, status, updated_at)` — active/archived filters
- Optional: `(user_id, type)`, `(user_id, reference)` for filters

---

## Flat / single-user scope

### Flat

Phase 20 BusinessContext is **flat**. Do **not** add:

```text
parent_context_id
client → matter hierarchy
context nesting
graph relationships
```

**Why deferred:** hierarchy adds cycle checks, recursive authorization, and list/filter complexity without unblocking the timeline/workspace MVP. Client vs matter can be expressed via `type` and `title`/`reference` until product proves nesting is required.

**Evolution path:** a later ADR may add nullable `parent_context_id` with same-owner and cycle constraints without renaming the aggregate.

### Single-user ownership

Phase 20 does **not** introduce organizations, teams, memberships, collaborators, ACL tables, shared contexts, or tenant administration.

**Evolution path:** future membership tables may reference `business_contexts.id` and `users.id` (ADR-013 foreshadowed this). Phase 20 schema must not pretend tenancy exists.

---

## Platform Owner semantics

```text
Platform Owner is an application administrative role.
Platform Owner does NOT implicitly bypass BusinessContext object ownership.
```

A principal with `application_role=owner` must **not** automatically:

- read another user's context
- modify / archive / restore another user's context
- associate another user's mailbox message or attachment analysis
- access another user's timeline or associations

`require_owner` remains limited to explicitly owner-gated admin endpoints (today: `/api/v1/admin/ping`). Context APIs use the ordinary `(iss, sub)` → `users.id` → row `user_id` ownership pattern. No global owner override in Phase 20.

---

## Communication provenance association

### Fact

There is no `communications` table. Do **not** invent `communication_id → communications.id`.

### Table: `business_context_communication_links`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Uuid` PK | no | `uuid4` |
| `business_context_id` | `Uuid` FK → `business_contexts.id` | no | See cascade |
| `user_id` | `Uuid` FK → `users.id` | no | Denormalized owner; must equal context.user_id; CASCADE with user |
| `connector_account_id` | `Uuid` | no | Owned connector; **no DB FK** (matches analyses / attachment_analyses provenance style) |
| `provider_message_id` | `Text` | no | Opaque provider message id; non-empty |
| `analysis_id` | `Uuid` | yes | Optional durable `analyses.id` snapshot at associate time; **no DB FK** |
| `associated_by_user_id` | `Uuid` | no | Must equal `user_id` in Phase 20 (manual self-associate) |
| `associated_at` | `DateTime(timezone=True)` | no | Timeline timestamp |
| `association_source` | `Text` | no | Phase 20: only `manual` |

### Cardinality

**Many-to-many provenance:**

```text
one (connector_account_id, provider_message_id) → many contexts
one context → many message provenances
```

A single email may belong to multiple matters/projects.

### Uniqueness

```text
UNIQUE (business_context_id, connector_account_id, provider_message_id)
```

**Why stable/sufficient:** Within one owned connector account, `provider_message_id` is the opaque provider identity already used by mailbox list/analyze, attachment analyses, and workflow execution targets (ADR-018/024). The triple scopes the link to one context without requiring a durable communication row.

### Association authorization (every mutate)

```text
1. Resolve caller → users.id via verified (iss, sub)
2. Load business_context WHERE id AND user_id
3. Load connector_account via get_owned(connector_account_id, user_id)
4. If analysis_id present: get_by_id_for_user(analysis_id, user_id)
5. Insert link with user_id / associated_by_user_id = caller
```

Additional rules:

- Context association does **not** grant mailbox read/send rights.
- Listing provider message bodies or attaching retrieve is **not** part of associate.
- Connector usability (`ACTIVE`, `mail.read`, credential) is required only when the product later *reads* mailbox content through existing mailbox APIs — not for creating a provenance link to an already-known opaque id from an owned connector.
- Phase 20 associate UX should normally start from an already-listed owned mailbox message (or owned analysis with connector provenance) so ids are not attacker-guessed in isolation; server still enforces ownership of connector and context.

### Association source / authority

Phase 20 check constraint:

```text
association_source IN ('manual')
```

Hard invariant:

```text
Persisted BusinessContext association is authoritative
only after an explicit authorized user action.
```

Future values (for example `ai_confirmed`, `external_mapping`) require an additive migration and must still pass through the same ownership-validated associate service. AI suggestions remain non-authoritative until confirmed (Phase 20F).

Removing a link deletes **only** the association row.

---

## Attachment association

### Phase 18 invariants (absolute)

```text
listing metadata ≠ retrieving bytes
context association ≠ Analyze
opening context ≠ retrieving attachment
timeline rendering ≠ retrieving attachment
association creation ≠ retrieving attachment
```

### Phase 20 lock

**No dedicated attachment-metadata association table in v1.**

Attachment relationship to a context is:

1. **Derived from message provenance:** associated `(connector_account_id, provider_message_id)` implies the message’s attachments may appear in the Documents UX via the **existing** Phase 18 metadata list API (`communications:read`, owned connector) — metadata only.
2. **Derived durable analyses:** `attachment_analyses` rows for the same user + connector + message appear in Documents / Analyses / timeline without copying payloads.
3. **No parallel Analyze path:** Analyze remains the existing mailbox attachment-analysis endpoint/service (policy → ClamAV → parser → AI → `attachment_analyses`).

### Explicit attachment retrieval prohibition

```text
No BusinessContext endpoint may retrieve mailbox attachment
content merely because an attachment is associated with a context
(or because its parent message is associated).
```

Conceptual flow for future XLSX:

```text
Context
  → message provenance link
  → attachment metadata (Phase 18 list)
  → user explicitly clicks Analyze
  → existing Phase 18 attachment-analysis path
  → exactly one attachment retrieved
  → policy → ClamAV → parser → AI
  → attachment_analyses row
  → context timeline/documents via derivation
```

### Attachment identity (when referenced)

Authoritative provider provenance keys already in the repository:

```text
connector_account_id
provider_message_id
provider_attachment_id
```

(`AttachmentMetadata.provider_attachment_id`; `attachment_analyses.provider_attachment_id`.)

Phase 20 does not persist a separate attachment-metadata link row. Phase 21 may add an optional explicit link table later if pinning a specific attachment without relying on message membership is required; it must still store only these opaque ids (never bytes).

---

## Analysis association

| Kind | Phase 20 relationship |
|---|---|
| `analyses` | **Derived** from communication links when `analyses.connector_account_id` + `analyses.message_id` (or equivalent provider message id field) match a link for the same `user_id`. Optional `analysis_id` on the link records provenance when associating from history. |
| `attachment_analyses` | **Derived** from communication links on `(user_id, connector_account_id, provider_message_id)`. |

Do **not**:

- copy analysis payloads into context tables
- require `business_context_id` on `analyses` / `attachment_analyses`
- use analysis association to authorize Analyze

One source message in many contexts ⇒ the same analysis appears in each context’s read model.

---

## Workflow association

| Decision | Lock |
|---|---|
| Required `business_context_id` on `workflow_actions` | **No** (breaks optional-context backwards compatibility) |
| Association table for workflows in Phase 20 | **Not required** |
| Relationship | **Derived** from matching `(connector_account_id, provider_message_id)` on owned `workflow_actions` to communication links |
| Authorization | Unchanged: Propose/Approve/Reject/Execute use existing permissions and `get_owned`; context membership never grants execute |

### If a communication is later removed from a context

- Workflow rows remain intact (auditability).
- They disappear from that context’s timeline/workspace view.
- They may remain visible under other contexts that still link the same provenance, or under global workflow history APIs.
- Approval/execution semantics are unaffected.

Preserve Analyze → Propose → Approve/Reject → Execute (ADR-015/017).

---

## Permission model

### Decision

**Reuse existing `communications:*` permissions. Do not introduce `communications:context` in Phase 20.**

| Operation class | Required permission(s) | Object ownership |
|---|---|---|
| Create / list / get / update / archive / restore context | `communications:analyze` | context `user_id` |
| Timeline / derived analyses / derived workflows view | `communications:analyze` | context `user_id` |
| Associate / remove communication provenance link | `communications:read` **and** `communications:analyze` | context + connector (+ optional analysis) |
| Open Documents via Phase 18 metadata list for an associated message | existing mailbox attachment metadata rules (`communications:read` + owned usable connector) | unchanged Phase 18 |
| Explicit Analyze attachment | existing Phase 18 (`communications:read` + `communications:analyze`) | unchanged |

### Rationale

- Contexts organize analysis/history work already gated by `communications:analyze`.
- Provenance association touches mailbox identifiers → also require `communications:read` (ADR-024 separation).
- A new Entra scope would force External ID app-registration churn on Azure and AWS without a demonstrated least-privilege need beyond the existing five scopes.
- Object ownership remains the primary isolation control; scopes are capability gates, not tenancy.

### Security consequence

A token with `analyze` but not `read` can manage empty/organizational contexts and view derived history already stored in ECI, but cannot create mailbox provenance links. A `read`-only token cannot manage contexts. Neither replaces `user_id` checks.

### Future extension path

If product later needs context management without analyze rights (for example clerks who only file mail), introduce `communications:context` via ADR amendment and IdP registration — not in Phase 20.

---

## Lifecycle / archive semantics

| Operation | Behavior |
|---|---|
| Create | `status=active`, `archived_at=null` |
| Update | Allowed only when `active` (title, description, reference, type) |
| Archive | `active` → `archived`; set `archived_at=now`; idempotent if already archived |
| Restore | `archived` → `active`; clear `archived_at`; supported in v1 |
| Default list | `status=active` only |
| List archived | Explicit filter (`status=archived` or `include_archived`) |
| New associations while archived | **Forbidden** (409) |
| Remove associations while archived | **Allowed** (cleanup) |
| Timeline while archived | **Readable** |
| Hard delete API | **Unsupported in Phase 20** |

Archive means hide/deactivate organizational context. It does **not** destroy source business records or mailbox provider content.

Workflows, analyses, and attachment analyses continue to exist independently of archive state.

---

## Cascade / deletion policy

| Relationship | ON DELETE | ORM | Notes |
|---|---|---|---|
| `business_contexts.user_id` → `users.id` | `CASCADE` | delete-orphan ok | User deletion removes contexts |
| `business_context_communication_links.business_context_id` → `business_contexts.id` | `CASCADE` | delete-orphan ok | Deletes **links only** if a context row is removed |
| `business_context_communication_links.user_id` → `users.id` | `CASCADE` | — | Consistency with other user-owned rows |
| `connector_account_id` on links | **No FK** | — | Provenance UUID; application validates `get_owned` |
| `analysis_id` on links | **No FK** | — | Same as `workflow_actions.analysis_id` |
| Context → `analyses` | **none** | — | Never cascade |
| Context → `attachment_analyses` | **none** | — | Never cascade |
| Context → `workflow_actions` | **none** | — | Never cascade |
| Context → connector accounts / credentials | **none** | — | Never cascade |
| Context → provider mailbox messages | **none** | — | ECI cannot/should not delete provider mail via archive |

Hard delete of BusinessContext (if ever added after Phase 20): may remove context row + association links only; must never delete analyses, attachment analyses, workflows, connectors, or credentials.

---

## Timeline / read model

### Decision

**Query/read model** assembled from durable records. **No** authoritative timeline/event-sourcing table in Phase 20.

### Reconstructible event types (v1)

| Event | Source |
|---|---|
| Context created | `business_contexts.created_at` |
| Context archived / restored | `archived_at` / `updated_at` + status (restore may only leave `updated_at` — acceptable) |
| Communication associated | `business_context_communication_links.associated_at` |
| Communication disassociated | **Not reconstructible after delete** — acceptable; no fabricated history |
| Analysis created (mailbox-backed) | `analyses.created_at` matching linked provenance |
| Attachment analysis created | `attachment_analyses.created_at` matching linked provenance |
| Workflow proposed / approved / rejected / executed / failed | workflow timestamps + status for matching provenance |

Do not invent historical events that were never persisted.

### Stable item identity

```text
context_created:<context_id>
context_archived:<context_id>:<archived_at_iso>
association:<link_id>
analysis:<analysis_id>
attachment_analysis:<attachment_analysis_id>
workflow:<workflow_action_id>:<status>
```

### Ordering

`event_at DESC`, then `item_id ASC` (or DESC — pick one in 20D and test). Paginate with `limit`/`offset` (max 100) or keyset on `(event_at, item_id)`.

Read-only. No writes through timeline endpoints.

---

## API authorization boundaries (architecture only)

Conceptual operations (paths illustrative; finalize in 20D):

| Operation | AuthN | Capability | Ownership | Cross-user |
|---|---|---|---|---|
| Create context | Bearer | analyze | bind `user_id` from resolver | — |
| List contexts | Bearer | analyze | `user_id` filter | empty if unmapped |
| Get context | Bearer | analyze | `id + user_id` | **404** |
| Update context | Bearer | analyze | owned + active | **404** |
| Archive / restore | Bearer | analyze | owned | **404** |
| Associate communication | Bearer | read+analyze | owned context + owned connector | **404** |
| Remove association | Bearer | read+analyze | owned link/context | **404** |
| Timeline | Bearer | analyze | owned context | **404** |

Match existing ECI convention: unknown and cross-user resources are indistinguishable (**404**, not 403). Do not rely on frontend filtering. Platform Owner does not widen these checks.

No BusinessContext route retrieves attachment bytes.

---

## AI-association policy

```text
AI MAY SUGGEST.
AI MUST NOT silently assign email, attachment, workflow,
task, deadline, or obligation to an authoritative BusinessContext.
```

Phase 20A–20E: manual `association_source=manual` only. Phase 20F may add non-authoritative suggestions; confirmation must call the same associate service.

Do not send BusinessContext metadata to AI providers merely because it exists. Future suggestion prompts must explicitly minimize and same-user-scope context fields; treat titles/descriptions as untrusted input (prompt-injection resistant handling).

---

## Multi-cloud implications

- Single Alembic revision applied independently to Azure PostgreSQL and AWS RDS.
- No cross-cloud replication.
- Domain/application layers remain free of Azure/AWS SDKs.
- No new cloud identity for contexts.

---

## Future Phase 21 compatibility (XLSX)

Locked path:

```text
BusinessContext
  → communication provenance link
  → Phase 18 attachment metadata list
  → explicit Analyze (Phase 18 path)
  → future XLSX parser (Phase 21)
  → attachment_analyses
  → context documents/timeline via derivation
```

Phase 20 must not persist XLSX bytes or spreadsheet-specific columns on `business_contexts`.

---

## Future Phase 22 compatibility (work items)

Future `work_items` (actions / deadlines / obligations) may add `business_context_id` + `user_id` FKs. No generic entity framework in Phase 20.

---

## Future Phase 23 compatibility (external systems)

Future mapping table (conceptual):

```text
external_context_mappings
  → business_context_id
  → integration/provider identity
  → external object identity
  → user_id
```

**No** vendor columns (`clio_matter_id`, `salesforce_account_id`, `sharepoint_id`) on `business_contexts`.

---

## Proposed Phase 20B database schema (specification only)

### `business_contexts`

- Purpose: durable organizational context owned by one application user
- PK: `id`
- FK: `user_id` → `users.id` `ON DELETE CASCADE`
- Checks: type set; status `active|archived`; archived_at null iff active
- Indexes: as above
- Unique: none beyond PK

### `business_context_communication_links`

- Purpose: authoritative manual provenance association
- PK: `id`
- FK: `business_context_id` → `business_contexts.id` `ON DELETE CASCADE`
- FK: `user_id` → `users.id` `ON DELETE CASCADE`
- Unique: `(business_context_id, connector_account_id, provider_message_id)`
- Checks: `association_source IN ('manual')`; non-empty `provider_message_id`
- Indexes: `(business_context_id, associated_at, id)`; `(user_id, connector_account_id, provider_message_id)`
- No FK to connector_accounts, analyses, provider systems

No other Phase 20B tables required for the locked architecture.

Illustrative next Alembic revision id: `20b0001` revising `19b0001` (final id chosen at 20B implementation).

---

## Domain contract (specification)

### Entities / values

- `BusinessContext` — aggregate root
- `BusinessContextType` — StrEnum (values above)
- `BusinessContextStatus` — StrEnum `ACTIVE` / `ARCHIVED`
- `BusinessContextCommunicationLink` — association entity
- `AssociationSource` — StrEnum with `MANUAL` only in Phase 20

### Validation rules

- title required 1–200 after trim
- description optional ≤4000
- reference optional ≤128
- type/status must be enum members
- archive/restore transitions only between active/archived
- associate requires owned context (active), owned connector, opaque non-empty message id

### Invariants

- `link.user_id == context.user_id == associated_by_user_id` (Phase 20)
- association does not imply mailbox I/O authorization beyond existing gates
- disassociate does not delete analyses/workflows/attachments/provider mail

---

## Repository / service boundary

| Layer | Phase 20B/C/D responsibility |
|---|---|
| Domain | Entities, enums, invariants; no FastAPI/SQLAlchemy/cloud/HTTP |
| Domain interfaces | `BusinessContextRepository`, link repository ports |
| Application | Create/update/archive/restore/associate services; ownership orchestration via `IdentityResolver` |
| Infrastructure | SQLAlchemy models, repository adapters, Alembic |
| API schemas | Pydantic request/response; no owner field from client |
| FastAPI | Routes + existing auth dependencies; 404 ownership misses |
| Frontend | API client + TanStack Query (20E); no security authority |

Dependency direction remains API → Application → Domain → Interfaces → Infrastructure/Providers.

---

## Threat-model lock

| Threat | Control |
|---|---|
| IDOR / context enumeration | `user_id` in every query; 404 indistinguishability |
| Cross-user context access | Ownership checks; Platform Owner non-bypass |
| Cross-user message association | `get_owned` connector + owned context |
| Foreign `connector_account_id` | Ownership miss → 404 |
| `provider_message_id` manipulation | Still requires owned connector; associate does not retrieve body; prefer UX from listed messages |
| Foreign attachment association | No attachment-link table; Analyze remains owned Phase 18 path |
| Context-based attachment retrieval | **Forbidden** by ADR; no such endpoints |
| Platform Owner privilege confusion | Explicit non-bypass; tests |
| Mailbox vs application identity confusion | ADR-021/027/028 retained |
| Association race / duplicate | Unique constraint; transactional insert; 409 or idempotent policy locked in 20D (prefer **409 Conflict**) |
| Cascade deletion | Matrix above; never cascade to analyses/workflows |
| AI unauthorized association | Manual-only until 20F; confirm path = manual service |
| Title/description prompt injection | Untrusted text; no auto AI send of context fields |
| Sensitive metadata in logs | Log ids/operations only; not titles/references/descriptions by default |
| Timeline leakage | Owned context gate before assembly; no cross-user joins |

No unresolved threat blocks Phase 20B under this lock.

---

## Privacy contract

| Data | Rule |
|---|---|
| title / description / reference | Sensitive business metadata; API as needed; **omit from ordinary logs** |
| provider message / attachment ids | Opaque; avoid logging unless required for support with redaction policy |
| timeline entries | Return structured summaries already stored; no raw bodies |
| exceptions | Generic details; no SQL/provider secrets |
| AI prompts | Do not include context metadata by default |
| Frontend cache | Clear on logout; do not persist context PII in `localStorage` |

---

## Backwards compatibility

```text
BusinessContext is optional.
```

Unaffected without context: mailbox listing, message analysis, attachment metadata listing, attachment analysis, workflow proposal/approval/rejection/execution/send, `/me`, admin ping.

No backfill of historical mail into contexts. No mandatory `business_context_id` on existing tables.

---

## Alternatives considered

- **Durable `communications` table** — rejected; invents a model the repository does not have; duplicates provider state.
- **One message → one context only** — rejected; overly rigid for real matters/projects.
- **Hierarchy / `parent_context_id` in v1** — deferred; complexity without MVP need.
- **Shared contexts / org ACL** — rejected for Phase 20; conflicts with current ownership isolation.
- **Platform Owner cross-user access** — rejected; ADR-028 non-widening.
- **New `communications:context` scope** — deferred; Entra churn without proven need.
- **Direct `business_context_id` on workflow_actions / analyses** — rejected for v1; breaks optional-context and invites cascade mistakes.
- **Authoritative timeline event table** — deferred; read model sufficient.
- **Attachment-metadata association table in v1** — deferred; derivation + Phase 18 list suffices for Phase 21 path.
- **Hard-delete context API in v1** — rejected; archive-only.
- **Vendor-specific columns on BusinessContext** — rejected; Phase 23 mapping table instead.

---

## Consequences

### Benefits

- Clear schema target for 20B without reopening ownership/cascade debates
- Preserves Phase 18 attachment security and Phase 19 RBAC meaning
- Cloud-neutral additive migrations from `19b0001`
- Natural Phase 21–23 extension points

### Trade-offs

- Documents-before-analyze rely on message association + Phase 18 metadata list (extra hop vs pinned attachment rows)
- Disassociation is not itself a durable timeline event
- Permission reuse means context filing requires analyze (and read for links)

---

## Migration implications

- Next implementing migration revises `19b0001`
- Empty production DBs and DBs with existing users/mailboxes/workflows must upgrade cleanly
- Downgrade drops link table then contexts
- Apply independently on Azure and AWS PostgreSQL

## Non-goals

XLSX/XLSM parsing; image AI/OCR; autonomous ingestion; autonomous context assignment; deadlines/obligations; calendar; DMS/CRM/Clio/Salesforce/SharePoint sync; risk/spam scoring; new workers/search platforms; cross-cloud replication; collaborative matters; org tenancy; live external-user testing (Phase 17D remains deferred).

## Related components

- [Phase 20 readiness assessment](../codex/reports/phase_20_readiness_assessment.md)
- [Phase 20 roadmap](../roadmap/phase-20-business-context-matter-intelligence.md)
- ADR-013, ADR-015, ADR-016, ADR-018, ADR-024, ADR-027, ADR-028
- `app/infrastructure/storage/models.py` (current aggregates)
- `app/application/services/connected_mailbox_access.py`
- `app/api/dependencies.py` (`require_owner`, permission gates)

## Security considerations

Summarized in threat-model and permission sections. Attachment byte retrieval via context APIs is an architecture **defect** if introduced later — treat as regression failure.

## Implementation note

Phase 20A locks architecture only. Phase 20B implements domain + persistence from this contract.
