# Phase 20 — Business Context & Matter Intelligence

## Objective

Establish a durable, user-owned **BusinessContext** foundation so ECI can organize mailbox communications (and later documents, work items, and external mappings) without weakening identity separation, mailbox isolation, Phase 18 attachment security, or approval-gated workflows.

```text
verified (iss, sub)
  → users.id
  → business_contexts.user_id
  → provenance links (connector_account_id + provider_message_id)
  → timeline read model (derived analyses / attachment_analyses / workflows)
```

Architecture: [ADR-029](../decisions/ADR-029-business-context-foundation-and-provenance-association.md).

Pre-implementation assessment: [Phase 20 readiness assessment](../codex/reports/phase_20_readiness_assessment.md) — **READY WITH CONDITIONS** (conditions resolved in 20A / ADR-029).

## Status

| Item | Status |
|---|---|
| Phase 19 — Platform Owner Identity & Application RBAC | **CLOSED / PASS** (unchanged) |
| Phase 18 — Secure Attachment Intelligence | **CLOSED / PASS** (unchanged) |
| Phase 17D External Business-User Verification | Deferred / out of current release scope |
| Phase 20 assessment | READY WITH CONDITIONS (resolved by 20A) |
| **20A** Architecture / ADR Lock | **CLOSED / PASS** |
| **20B** BusinessContext Domain & Persistence Foundation | **CLOSED / PASS** |
| **20C** Provenance Associations | **CLOSED / PASS** |
| **20D** Context API & Authorization | **CLOSED / PASS** |
| **20E** Context Workspace & Timeline Frontend | **CLOSED / PASS** |
| **20F** AI-Assisted Context Suggestions | **CLOSED / PASS** |
| **20G** Hardening / Regression / Documentation / Cloud Validation | Local hardening — **PASS**; Azure live validation — **PASS**; AWS live validation — **PASS** |
| Phase 20 overall | **CLOSED / PASS** |

Phase 20 is **CLOSED / PASS** after local hardening plus authorized Azure and AWS live validation.

### Longer-term product sequence (context only)

```text
Phase 20 — Business Context / Matter Intelligence
Phase 21 — XLSX / Tabular Intelligence
Phase 22 — Action / Deadline / Obligation Tracking
Phase 23 — DMS / CRM / Case-System Integration
Phase 24 — Communication Risk Intelligence
Phase 25 — Optional Multimodal / Image Intelligence
```

Phases 21–25 are **not** in Phase 20 scope.

## Locked architecture (authoritative)

Recorded in ADR-029. Summary:

| Decision | Lock |
|---|---|
| Aggregate | Flat `BusinessContext` / table `business_contexts` |
| Ownership | Single-user `user_id` = authenticated `users.id` from `(iss, sub)` |
| Platform Owner | Does **not** bypass object ownership |
| Hierarchy / shared contexts | Out of scope |
| Communications table | **Does not exist**; do not invent one |
| Message association | `business_context_communication_links` on `(connector_account_id, provider_message_id)` |
| Cardinality | Many-to-many; UNIQUE `(business_context_id, connector_account_id, provider_message_id)` |
| Association authority | Explicit user action; Phase 20 source `manual` only |
| Attachment association | Derived via message link + Phase 18 metadata/analyze; no context byte retrieve |
| Analyses / workflows | Derived into timeline; no required FK on those tables |
| Permissions | Reuse `communications:analyze` (+ `communications:read` for provenance links); **no** new `communications:context` |
| Lifecycle | `active` ↔ `archived` (+ `archived_at`); hard delete unsupported |
| Cascade | Context/link teardown never deletes analyses, workflows, connectors, or provider mail |
| Timeline | Read model only; not event sourcing |
| AI | Suggest later; never silent authoritative assign |
| Multi-cloud | Same schema on independent Azure/AWS PostgreSQL |

### Six readiness conditions — resolution

| # | Condition | Resolution |
|---|---|---|
| 1 | Lock provenance association model | ADR-029 communication link table + ownership checks |
| 2 | Cascade must not destroy analyses/workflows/mailbox data | Cascade matrix; archive-only API; no FK cascades to history tables |
| 3 | Platform Owner must not bypass object ownership | Explicit ADR-029 + ADR-028 non-widening |
| 4 | Shared contexts and hierarchy out of scope | Locked flat + single-user |
| 5 | Permission reuse vs `communications:context` | **Reuse** existing scopes (see ADR-029) |
| 6 | Context APIs must not retrieve attachment bytes | Explicit prohibition; Analyze stays on Phase 18 path |

## Critical repository fact

```text
There is NO durable communications table.
```

Mailbox communications are provider-backed resources identified through owned connector provenance:

```text
connector_account_id + provider_message_id
```

## Implementation slices

### 20A — Architecture / ADR Lock

**Status:** **CLOSED / PASS**

**Objective:** Resolve readiness conditions and publish the authoritative architecture contract.

**Scope:**

- ADR-029
- This Phase 20 roadmap
- Roadmap index / ADR index updates
- Preserve readiness assessment

**Non-goals:** Schema, APIs, frontend, AI, cloud, mailbox I/O.

**Completion criteria:**

- All six conditions explicitly resolved
- ADR Accepted as architecture lock
- No production implementation files changed

**Dependencies:** Phase 19 CLOSED; assessment READY WITH CONDITIONS.

**Security invariants:** Documented only; unchanged at runtime.

---

### 20B — BusinessContext Domain & Persistence Foundation

**Status:** **CLOSED / PASS**

**Objective:** Implement domain types, repository ports, SQLAlchemy models, and Alembic migration from `19b0001` for `business_contexts` (and empty-ready link table if sequenced here — prefer contexts first, links in 20C if split keeps reviews smaller; **default: contexts in 20B, links in 20C**).

**Scope:**

- Domain enums/entities/validation
- `BusinessContextRepository` (+ unit/postgres tests)
- Alembic revision creating `business_contexts`
- Ownership filtering patterns matching existing repositories

**Non-goals:** HTTP routes; frontend; association mutate APIs; AI.

**Completion criteria:**

- Migration upgrades/downgrades from `19b0001`
- Create/read/update/archive/restore persistence tests
- Cross-user isolation tests
- Ruff + pytest green offline

**Dependencies:** 20A.

**Security invariants:** `user_id` always from identity mapping; no email ownership.

**Delivered:**

- Domain: `BusinessContext`, `BusinessContextType`, `BusinessContextStatus`
- Persistence: `business_contexts` table + SQLAlchemy repository + UoW wiring
- Alembic head: `20b0001` (revises `19b0001`)
- No `business_context_communication_links` (deferred to 20C)

---

### 20C — Provenance Associations

**Status:** **CLOSED / PASS**

**Objective:** Persist and enforce `business_context_communication_links` with ownership and uniqueness.

**Scope:**

- Link table migration (if not in 20B)
- Associate / disassociate application services
- Unique constraint and race tests
- Derivation helpers for analyses / attachment_analyses / workflows (no schema change to those tables)

**Non-goals:** Public HTTP (unless thin internal needed); frontend; AI confirm; attachment byte I/O.

**Completion criteria:**

- User A cannot link User B connector/message/context
- Duplicate link → conflict
- Disassociate deletes link only
- Archived context rejects new links

**Dependencies:** 20B.

**Security invariants:** Phase 18 retrieve never called from associate paths.

**Delivered:**

- Domain: `BusinessContextCommunicationLink`, `AssociationSource.MANUAL`
- Application: `BusinessContextCommunicationLinkService` (associate / list / remove)
- Persistence: `business_context_communication_links` + SQLAlchemy repository + UoW wiring
- Alembic head: `20c0001` (revises `20b0001`)
- Ownership-only connector validation (usability not required for association)
- Optional `analysis_id` without DB FK; same-user provenance match required
- No `communications` table; no attachment-link table; no HTTP routes

---

### 20D — Context API & Authorization

**Status:** **CLOSED / PASS**

**Objective:** Expose FastAPI routes under `/api/v1` with existing auth dependency patterns.

**Scope:**

- CRUD/archive/restore/list/get
- Associate/remove/list communication provenance links
- OpenAPI schemas; 401/403/404/409/503 semantics
- Integration tests for IDOR and permission matrix

**Deferred to 20E:** Timeline read-model endpoint and frontend workspace (slice DoD kept API/authorization focused; roadmap originally listed timeline under 20D).

**Non-goals:** Frontend; AI suggestions; new OIDC scope registration; hard-delete context API; attachment retrieval via contexts.

**Completion criteria:**

- Permission matrix matches ADR-029
- Platform Owner non-bypass proven
- No attachment content endpoints under contexts

**Dependencies:** 20C.

**Security invariants:** 404 indistinguishability; capability + ownership dual gate.

**Delivered:**

- Application: `BusinessContextService` (create/list/get/update/archive/restore)
- HTTP: `/api/v1/contexts` CRUD/lifecycle + `/communications` association routes
- Auth: context CRUD → `communications:analyze`; association → `communications:read` + `communications:analyze`
- Alembic head unchanged: `20c0001`
- No timeline endpoint; no frontend; no `communications:context` scope

---

### 20E — Context Workspace & Timeline Frontend

**Status:** **CLOSED / PASS**

**Objective:** Minimal React UX for list, create, workspace, archive/restore, manual associate, timeline.

**Scope:**

- Routes under `/contexts` (exact paths chosen in slice)
- TanStack Query hooks + API client
- Manual associate from mailbox/workspace without redesigning OAuth
- Loading/error/empty states consistent with Phase 15 patterns
- Timeline read-model endpoint `GET /api/v1/contexts/{context_id}/timeline`

**Non-goals:** Actions/deadlines/external systems sections; AI suggest UX; redesign unrelated pages.

**Completion criteria:**

- Authenticated owner flows work offline-mocked
- Unauthorized/404 handled
- Logout clears context query cache

**Dependencies:** 20D.

**Security invariants:** Frontend never authoritative for ownership.

**Delivered:**

- Backend: `ContextTimelineService` read model + `GET /api/v1/contexts/{context_id}/timeline`
- Timeline sources: context created/current archive, communication links, mailbox analyses (provenance present), attachment analyses, workflow transitions (execution target present)
- Frontend: `/contexts` list + `/contexts/:contextId` workspace (Overview / Communications / Timeline)
- Manual associate from selected mailbox message (`Add to Context`); remove association is non-destructive
- Context CRUD/lifecycle works without mailbox connection
- Alembic head unchanged: `20c0001` (no timeline table / no migration)

---

### 20F — AI-Assisted Context Suggestions

**Status:** **CLOSED / PASS**

**Objective:** Optional non-authoritative suggestions; human confirm creates `manual`-equivalent authoritative link via same service (source may become `ai_confirmed` only after additive migration approved in this slice).

**Scope:**

- Suggestion generation boundaries; same-user candidates only
- Confirm → associate service
- Privacy-safe prompts

**Non-goals:** Silent assignment; cross-user candidates; new workers.

**Completion criteria:**

- AI cannot persist association without confirm
- Offline tests with mock AI

**Dependencies:** 20E recommended (or 20D minimum).

**Security invariants:** ADR-029 AI policy.

**Delivered:**

- Provider-neutral `AIProvider.suggest_business_context` (Mock / Foundry / Bedrock)
- Application: `BusinessContextSuggestionService` (owned analysis + owned active candidates only)
- HTTP: `POST /api/v1/contexts/suggestions` (read+analyze); suggestions never create links
- Frontend: explicit **Suggest Context** in Add-to-Context panel; confirm uses existing associate API
- AI suggestions are advisory; no persistent suggestion table; Alembic head unchanged: `20c0001`
- Association source remains `manual` (no `ai_confirmed` migration)

---

### 20G — Hardening / Regression / Documentation / Cloud Validation

**Status:**

```text
Local hardening — PASS
Azure live validation — PASS
AWS live validation — PASS
```

**Objective:** Security matrix, privacy logging regression, docs reconciliation, Alembic validation on Azure/AWS PostgreSQL when authorized, Phase 20 closure.

**Scope:**

- Full offline regression (pip check, ruff, pytest, frontend tests as applicable)
- Documentation updates for endpoints/roadmap closure
- Operator-authorized cloud migrate validation (no cross-cloud replication)
- Confirm Phase 18/19 invariants unchanged

**Non-goals:** Phase 21 XLSX implementation; Phase 17D; starting managed databases or live Foundry/Bedrock without explicit authorization.

**Local hardening delivered:**

- Cumulative ADR-029 architecture audit (ownership, cascade, timeline, AI non-authority)
- Identity / Platform Owner / mailbox isolation / Phase 18 attachment / workflow regressions
- Migration chain verification (`19b0001` → `20b0001` → `20c0001`; single head `20c0001`)
- Frontend error-mapping hardening for communications list / disassociate
- Additional suggestion bounds and prompt-injection regression tests
- API docs aligned through Phase 20F suggestions

**Azure live validation — PASS (authorized Phase 20G):**

- Schema: `19b0001` → `20c0001` on Azure PostgreSQL `eci-pg-dev-susanta` (tables `business_contexts`, `business_context_communication_links`)
- Backend: ACA image `eci-api:ed5eebc-p20g` / revision `eci-api-dev--0000011`; `/health` + `/api/v1/readiness` OK
- Frontend: `npm run build:azure` → SWA `eci-web-dev`; Contexts navigation present
- Authentication: Entra External ID operator login; protected API smoke OK (application login independent of mailbox)
- BusinessContext: create / list / read / update / archive / restore without mailbox requirement
- Association: owned Outlook message → Add to Context → list → duplicate conflict → Remove from Context (provider email untouched)
- Timeline: persisted `Context created` event only (no fabricated archive/restore history)
- Foundry suggestion: live `Suggest Context` advisory response; no communication link created by suggestion alone; manual Associate required
- Attachment regression: selected message had no attachments; context open/timeline/suggestion paths did not retrieve attachment bytes
- Workflow regression: Propose → Approve / Reject presented; Reject used; no Execute/Send
- Platform Owner live cross-user Context isolation: not exercised (no safe second test identity); rely on automated coverage
- New Azure infrastructure / secrets / IAM: none
- AWS: **not** touched

**AWS live validation — PASS (authorized Phase 20G):**

- Schema: `19b0001` → `20c0001` on RDS `eci-pg-dev` (eu-south-2); tables `business_contexts`, `business_context_communication_links`; `eci_app` grants OK
- Operator migrate note: app Secrets Manager `DATABASE_URL` `GetSecretValue` denied to `eci-developer`; migration used RDS `MasterUserSecret` as `eciadmin` (one-shot operator path)
- Backend: ECR `eci-api-dev:ed5eebc-p20g` (`sha256:6b6a5ea51a8735546a666542900cd0b53f3b9a6e1628d29cc5e1a45694dddfe6`); task definition `eci-api-dev:12`; service `eci-api-dev` rollout COMPLETED / HEALTHY (`desired/running 1/1`)
- Frontend: `npm run build:aws` → S3 `eci-web-aws-dev-034456343525` (new assets uploaded; `--delete` AccessDenied so prior SPA objects retained); CloudFront SPA invalidation `I8VIGBIL24QLDA2Z5X4D3KROPH` Completed
- Health: API CloudFront `/health`, `/api/v1/health`, `/api/v1/readiness` → 200
- Authentication: Entra External ID operator login on SPA; `/api/v1/me` returned `application_role=user` (mailbox login remains separate)
- BusinessContext: create / list / read / update without mailbox requirement; smoke context `Phase 20 AWS Validation` (`P20G-AWS-SMOKE`) archived at end of smoke
- Association: owned Gmail message → Add to Context → list → duplicate conflict → Remove from Context (provider email untouched); `link_count` returned to 0
- Timeline: workspace Timeline tab exercised on owned context (read model only)
- Bedrock suggestion: live `Suggest Context` advisory response (`AI suggestion · review before associating` / no suitable match); `link_count` unchanged by suggestion alone; manual Associate remains the authority
- Attachment regression: JPEG metadata listed; image analysis unavailable with current AI provider (expected); context paths did not retrieve attachment bytes for association/suggestion
- Workflow regression: Propose → Reject (`Status: Rejected`); no Execute/Send
- CloudWatch `/ecs/eci-api-dev`: expected Gmail REAUTH recovery and duplicate-link conflict info events only; no Phase 20 API failure signature for suggest/propose/archive
- New AWS infrastructure / secrets / IAM: none
- Azure: **not** mutated (left Running per operator instruction)

**Completion criteria:**

- Local offline checklist PASS
- Azure live validation PASS
- AWS live validation PASS
- Phase 20 marked **CLOSED / PASS**

**Dependencies:** 20F.

**Security invariants:** Full threat-model regression from ADR-029.

**Post-validation runtime:**

AWS ECS/RDS and Azure ACA/PostgreSQL remain running until the operator explicitly requests stop/scale-down. See deployment runbooks.

**Phase boundaries retained:**

- Phase 21: XLSX / XLSM remains unsupported / fail-closed (no `openpyxl`)
- Phase 22: no durable actions / deadlines / obligations
- Phase 23: no DMS / CRM / Clio / Salesforce / SharePoint context mapping

## Explicit non-goals (entire Phase 20)

- XLSX / XLSM parsing; image AI; OCR
- Autonomous mailbox ingestion / bulk analysis / background sync
- Autonomous context assignment
- Deadlines, reminders, obligations, calendar
- DMS / CRM / Clio / Salesforce / SharePoint sync
- Communication-risk / spam scoring
- New workers (Celery/Kafka/Redis/K8s) or search platforms
- Cross-cloud DB replication
- Collaborative multi-user matters / organization tenancy
- Live external-user testing (Phase 17D deferred)
- New `communications:context` Entra scope (unless a future ADR revises ADR-029)

## Pre-existing documentation debt (partially addressed in 20G)

Identified in the readiness assessment:

- Phase 18 roadmap still mentions historical Alembic head `18d0001` in places (current head is `20c0001`) — historical narrative retained; not rewritten as a drive-by
- `docs/api/endpoints.md` intro updated through Phase 20F in 20G

Remaining debt outside Phase 20 closure: historical Phase 18/16 schema-head wording in older roadmap sections; optional tab ARIA/keyboard polish on context workspace.

## Recommended next action

```text
Wait for operator instruction before stopping Azure and/or AWS
development resources (cost-aware scale-down / stop).
```

Do **not** start Phase 21 until explicitly instructed.