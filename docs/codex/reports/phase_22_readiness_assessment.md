# Phase 22 — Action, Deadline & Obligation Tracking: Readiness Assessment

Assessment date: 2026-09-26. Baseline: local `master`, commit `bfc68b0`.

**Verdict: READY WITH CONDITIONS.** The existing architecture supports a separate, user-owned business tracking aggregate without changing mailbox access, attachment processing, or reply execution. Phase 22 is ready for an explicitly authorized architecture-lock slice (22A), but implementation must wait for the operator decisions in section 10. This report approves no candidate capability and starts no implementation.

## 1. Scope, evidence, and repository state

The assessment inspected local source, tests, migration scripts, ADRs, frontend contracts, CI configuration, and Phase 20/21 documentation. `HEAD` matches the supplied Phase 21 closure commit; `git status` reports `master...origin/master` with only pre-existing untracked `AGENTS.md` before this report. That file is preserved. The remote-tracking status is local information, not a fresh remote verification.

Phase 20 is documented CLOSED/PASS. Phase 21 is CLOSED/PASS for its delivered XLSX scope. Phase 17D remains deferred; it is not a prerequisite for local architecture work and is not silently included in Phase 22. GitHub Actions success is supplied baseline information, not independently rechecked here.

The [Phase 21G closure report](phase_21g_report.md#66-evidence-boundaries-and-remaining-limitations) distinguishes accepted operator-reported Azure/AWS completion from earlier agent-observed evidence. It does not claim exhaustive live security, concurrency, memory, load, failure, or accessibility coverage. Historical results are **2,681 backend tests, including 94 PostgreSQL tests, and 369 frontend tests across 30 files**. These are prior results, not tests run by this assessment.

No Azure/AWS access, network research, paid AI calls, mailbox retrieval, attachment retrieval, database connection, migration execution, application test execution, commit, or push was performed. Repository migration head was determined from revision declarations, not a live database. Only this report is added.

### Primary evidence map

Paths below refer to inspected implementation or existing tests, not proposed files.

| Area | Evidence | Architectural implication |
|---|---|---|
| Phase 20 | [ADR-029](../../decisions/ADR-029-business-context-foundation-and-provenance-association.md), [Phase 20 roadmap](../../roadmap/phase-20-business-context-matter-intelligence.md) | Flat, optional, single-user context; provenance links; advisory suggestions; no implicit task creation |
| Phase 21 | [Phase 21 roadmap](../../roadmap/phase-21-xlsx-tabular-intelligence.md), [closure](phase_21g_report.md#67-final-closure-and-documentation-only-handoff) | Bounded XLSX intelligence reuses attachment analyses; potential dates/actions remain observations |
| Identity | [ADR-013](../../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md), [ADR-028](../../decisions/ADR-028-platform-owner-identity-and-application-rbac.md); `app/core/security.py`, `app/application/services/identity.py`, `app/api/dependencies.py` | Verified `(iss, sub)` resolves internal ownership; capability permissions and persisted application role are separate |
| Reply workflow | [ADR-015](../../decisions/ADR-015-approval-gated-workflow-actions.md), [ADR-016](../../decisions/ADR-016-workflow-persistence-and-analysis-provenance.md), [ADR-018](../../decisions/ADR-018-workflow-execution-target-provenance.md); `app/domain/models/workflow.py`, `app/application/services/workflow_actions.py`, `workflow_action_execution.py` | Explicit proposal, immutable reply snapshots, approval, separate controlled execution |
| Analysis outputs | `app/domain/models/analysis.py`, `tabular_analysis.py`; `app/domain/interfaces/analysis_repository.py`, `attachment_analysis_repository.py` | Existing action suggestions lack independent identity, status, and confirmed deadline semantics |
| Persistence | `app/infrastructure/storage/models.py`, `repositories/{analysis,attachment_analysis,workflow_action,business_context}.py`, `unit_of_work.py`; `alembic/versions/` | Owned repositories, portable JSON/JSONB, caller-owned transaction, no communications table |
| Context association/timeline | `app/application/services/business_context_communication_links.py`, `business_context_suggestions.py`, `context_timeline.py`; `app/api/routes/business_contexts.py` | Ownership and provenance checks reusable; timeline is a projection, not an event journal |
| Attachment boundary | `app/application/services/connected_mailbox_attachment_analysis.py`, `attachment_analysis.py`; `tests/integration/test_phase21d_xlsx_analysis.py` | Explicit Analyze alone retrieves bytes; CLEAN scan gates parser, then AI and successful persistence |
| Provider contract | `app/domain/interfaces/ai_provider.py`, `app/providers/{mock,microsoft_foundry,amazon_bedrock}/provider.py`, `app/providers/common/tabular_{input,output,prompts}.py` | Provider-neutral analysis and tabular results; no tracking mutation method |
| Frontend | `frontend/src/api/{client,contexts,mailbox,attachments,workflowActions}.ts`, `hooks/useContexts.ts`, `pages/ContextWorkspacePage.tsx`, `components/mailbox/{ActionItemsList,TabularAnalysisPanel,WorkflowReviewPanel}.tsx`, `App.tsx` | Typed client, React Query, permission-aware views, explicit confirmation, cache cleanup patterns |
| Regression evidence | `tests/integration/test_business_contexts.py`, `test_workflow_execution_boundary.py`, `test_phase21d_xlsx_analysis.py`; `tests/unit/application/test_business_context_suggestions.py`; `tests/unit/providers/test_tabular_analysis_parity.py`; `tests/postgres/test_business_context_repository.py`, `test_phase21f_atomicity.py`; `frontend/src/test/{contexts,tabularAnalysis,workflowReview}.test.tsx` | Existing fixtures and boundary tests can be extended; they do not yet test durable tracking |

## 2. Current baseline and gap analysis

### Three meanings of action must remain separate

| Concept | Current behavior | Phase 22 treatment |
|---|---|---|
| `ActionItem` | AI result with `description`, optional free-text `owner`, optional `due_at`, optional priority; persisted inside analysis JSON and rendered as a list | Advisory source only. Its owner text is never an internal user ID or assignee authorization. Its datetime does not distinguish date-only intent or require explicit timezone confirmation |
| `WorkflowAction` | Durable `reply` proposal with analysis provenance, owner, proposed/approved reply snapshots and optional connector/message execution target | Preserve unchanged. Never add task/obligation kinds or task completion to its state machine |
| Proposed `BusinessWorkItem` | Not implemented | Separate durable record of something the user chooses to track; completing it records a human declaration, not execution of a communication or verification of a legal obligation |

The existing workflow transitions are `pending → approved/rejected`, `approved → executing`, and `executing → executed/failed`; rejected/executed/failed are terminal. Repository updates compare the expected status. Execution has its own authorization and mailbox eligibility checks. Phase 22 must not reuse this state machine for editable tasks, reopenable obligations, or deadlines.

`CommunicationAnalysisWorkflowService` orchestrates analysis persistence; its name does not make it a business workflow/task engine. `workflow_actions.analysis_id` refers to communication analysis provenance, never an attachment-analysis ID. Analysis deletion does not invalidate the existing reply snapshots.

### Reusable architecture and missing capabilities

| Capability | Safely reusable | Gap / required addition |
|---|---|---|
| Durable tracking | UUIDs, Pydantic domain validation, repositories, SQLAlchemy, unit of work | New aggregate, owned table, explicit lifecycle and mutation services |
| BusinessContext association | Owned active-context lookup; optional context UX | Direct optional association for a work item; not inferred from a shared message |
| Source provenance | Connector/message/attachment opaque identifiers; owned analysis lookup | Typed tracking source references and confirmation locator; no FK to nonexistent communications |
| Dates/deadlines | UTC timestamps for recorded events | Date-only value, explicit IANA zone, aware timed value, DST validation and overdue policy |
| AI confirmation | Phase 20 advisory suggestion/explicit mutation separation | Review form, server-validated candidate locator, atomic confirmed creation |
| Ownership | `IdentityResolver`, owner-scoped SQL, 404 isolation, capability dependencies | Apply to every new list, lookup, filter, source, context and event query |
| Concurrency | Workflow conditional-update pattern | Monotonic version for editable fields and lifecycle; creation idempotency |
| Timeline | Existing typed read model and deterministic ordering | Persist real work-item events; indexed retrieval; no invented restore/edit history |
| Frontend | Typed `EciApiClient`, React Query, forms, errors, confirmation dialogs, permission gates | Global tracking list/detail/editor; optional context tab; conversion from existing results |
| Provider support | Mock/Foundry/Bedrock analysis and tabular contracts | No provider change needed for the recommended first scope |

`analyses` stores structured summary, action items, draft reply and optional mailbox provenance, not raw message bodies. `attachment_analyses` stores structured results and metadata, including nullable `tabular_result`. XLSX uses `potential_dates`, `potential_amounts`, and `potential_action_mentions` string lists; its ordinary `action_items` is empty. The arrays do not encode which date belongs to which action, stable cell coordinates, legal force, or confirmed ownership. Do not join them by array position or automatically parse them into commitments.

BusinessContext currently offers overview, communications, and timeline frontend tabs. It has no implemented tracking workspace. Context archive is independent of linked analyses/workflows. The timeline follows owned communication links to durable analyses, attachments, and workflows; unlinking removes those derived appearances without deleting the source records.

The timeline returns a bounded page but internally loads all links and pages through user analyses/workflows before sorting. Bounded response size is not bounded query work. Adding a long-lived tracking history must use context-filtered event queries rather than another full-owner scan; broader timeline optimization should be measured and separately scoped.

### Migration baseline

The repository has one linear head: **`21d0001`**, parent `20c0001`; the preceding context revisions are `20b0001` and `20c0001`, after `19b0001`. `21d0001` extends the attachment kind check for XLSX and adds nullable JSON/JSONB `tabular_result`. Its downgrade refuses while XLSX rows exist. No migration or live database head was executed/read here.

New tracking migrations should descend from `21d0001`, create empty tables, and leave Phase 20/21 data and analysis JSON semantics intact. **No backfill from AI output**: historical detection is not historical human confirmation.

## 3. Candidate product scope and recommended first boundary

All scope below is proposed, pending section 10 approval.

Recommend a single-user tracking MVP with actions and obligations, optional due information, manual create/edit, explicit create-from-existing-analysis, zero or one BusinessContext, status/archive management, source references, bounded lists/filters, a global tracking view and context integration. An obligation means a user-recorded duty or commitment; ECI does not determine that it is legally binding or independently fulfilled.

Recommend representing a deadline as due information on a work item, not a third independently managed aggregate. A date-only reminder without a described action/obligation should not silently become a business commitment. A user can instead deliberately create an action describing what is due. If standalone milestones, multiple deadlines per obligation, recurring duties, or one obligation with many fulfillment actions are required, approve a richer model before schema work.

Defer assignment to other users, team sharing, tenancy, reminders/notifications, calendars, escalation jobs, recurrence, dependencies, automatic compliance determinations, external task-system sync, automatic sending, and automatic workflow linkage/completion. These are not necessary for durable personal tracking and are not authorized by the phase title.

## 4. Proposed domain and data architecture

### Model choice

Recommend `BusinessWorkItem` / `business_work_items`, with `kind = action | obligation` and a shared lifecycle. “Action” can remain the user-facing label; “work item” avoids confusion in code and API names with `WorkflowAction`.

Alternatives considered: extending `workflow_actions` would mix reply authorization with human tracking and is rejected; three independent action/deadline/obligation aggregates add relationships and completion rules not yet justified; storing more JSON in `analyses` would prevent independent ownership/lifecycle and make source deletion unsafe. A typed work item plus typed due fields is the smallest viable new domain. Kind is selected at creation and immutable in the proposed first version.

### Proposed tables

**`business_work_items`**:

| Fields | Proposed rules |
|---|---|
| `id`, `user_id` | UUID PK; server-resolved owner FK to `users.id`, user-deletion CASCADE; no client-set owner |
| `kind` | Text + check constraint: `action`, `obligation`; Python `StrEnum`, not PostgreSQL ENUM |
| `title`, `description` | Trimmed nonblank title, 1–200 characters; optional description up to 4,000; user-reviewed business text only |
| `business_context_id` | Nullable FK to `business_contexts.id`; same-owner validation, active target on new association; `ON DELETE SET NULL`, never cascade deletion of work items |
| `status` | `open`, `in_progress`, `completed`, `cancelled`; default `open` |
| `due_kind`, `due_date`, `due_at`, `due_timezone` | Discriminated `none/date/datetime` rules below; SQL DATE for date-only; aware timestamp for timed deadline; IANA zone string up to 64 characters |
| `completed_at`, `cancelled_at` | UTC lifecycle timestamps paired with current terminal status; previous transitions live in events |
| `archived_at` | Nullable UTC timestamp independent of status; archive does not mean completed |
| `created_at`, `updated_at`, `version` | Server UTC timestamps; integer version starts at 1 and increases on actual mutations |
| `creation_origin`, `confirmed_by_user_id`, `confirmed_at` | `manual` or `ai_confirmed`; confirmed actor equals owner; explicit human-confirmation timestamp required for `ai_confirmed`, absent for manual |
| `creation_key`, `creation_request_hash` | Required bounded opaque idempotency key and canonical request digest; unique `(user_id, creation_key)` |
| `origin_candidate_key` | Nullable server-derived locator digest; unique `(user_id, origin_candidate_key)` when non-null; details below |

Use DB checks for enum values, text bounds where portable, due-field exclusivity, status/timestamp pairing, archive timestamp validity where applicable, positive version, and confirmation-field pairing. Repository and domain validation must agree. Add `(id, user_id)` uniqueness for composite ownership FKs from child tables. Proposed indexes: `(user_id, created_at, id)`, `(user_id, status, due_at, id)`, `(user_id, status, due_date, id)`, and `(user_id, business_context_id, created_at, id)`; finalize against actual query plans. Archive filtering may justify partial indexes after measurement.

Context FK existence alone does not enforce same owner. The service must owner-scope and lock/recheck the target context within the mutation transaction, consistently with its archive writes. Context ownership is not editable. No new sharing model or global administrative override is implied.

**`business_work_item_sources`**:

- UUID PK, `work_item_id`, `user_id`, `source_kind`, optional `analysis_id` or `attachment_analysis_id`, optional connector/message/attachment identifiers, optional `candidate_field`, `candidate_index`, `candidate_digest`, and server `linked_at`.
- Composite `(work_item_id, user_id)` FK to the owned item with CASCADE; child owner must match parent. Typed checks distinguish communication-analysis, attachment-analysis and direct communication provenance. A source cannot claim both analysis types.
- Recommend zero sources for a manual item, up to ten explicitly selected sources at creation, and at least the validated origin source for AI confirmation. Later source editing/merging is deferred; changing context does not rewrite sources.
- Connector/message identifiers form a pair; an attachment identifier additionally requires that pair. Owned direct-text analyses are valid without mailbox provenance. Analysis-derived identifiers are copied by the server, not accepted as authority from AI or client.
- Analysis/connector identifiers remain opaque provenance without deletion-cascading FKs, matching ADR-016/018/029 history independence. They must be verified through owned repositories when initially linked. There is no `communications` table or FK to create.
- No bodies, extracted text, cell values, full analysis snapshots, arbitrary URLs, prompts, or raw provider responses. A bounded confirmed title/description is intentional user-authored tracking data, not permission to copy the entire source.
- Reject duplicate sources within one item using a server canonical source key and unique `(work_item_id, source_key)`. Preserve exact opaque provider ID case/meaning; do not normalize as email addresses.

**`business_work_item_events`**:

- UUID PK, owned item composite FK, `user_id`, `actor_user_id`, event type, server UTC `occurred_at`, resulting item version, optional context-at-event ID, and bounded typed transition metadata.
- Events: created, edited, status_changed, archived, restored, context_associated, context_disassociated. Store old/new statuses and due values when changed, changed-field names for text edits, and context IDs for association changes. Do not retain previous title/description bodies in event payloads.
- Events are appended by the service in the same unit of work as the item mutation. No public event-create endpoint. This is a small audit journal, not an event-sourced rewrite of the application.
- Index `(user_id, context_at_event_id, occurred_at, id)` and `(user_id, work_item_id, occurred_at, id)`. Use event sequence/ordinal with version if one mutation produces multiple events; enforce unique `(work_item_id, item_version, event_ordinal)`.
- Context IDs on historical events are opaque, not deletion-cascading associations; timeline access still requires a currently owned context. User deletion removes owned tracking rows and their events/sources; ordinary item archive does not.

### Action, obligation, and context relationships

An item has one kind, one lifecycle, zero or one due value, zero or one current context, and bounded provenance sources. Source message membership in a context does not authorize or establish item membership. Creating an item in a context does not automatically link its source communication to that context.

Existing source links and new direct item/context association are independent. Removing a communication link must not remove a confirmed item. Moving an item between owned active contexts is an explicit versioned mutation; record removal from the old context and addition to the new one. Archiving a context does not cancel, complete, or archive its items. Recommend allowing existing items to progress or be detached from an archived context, while refusing new associations to that context. Make this behavior visible in the UI.

If context hard-delete is introduced later, preserve work items with a null current context. Existing history is not rewritten into another context. Phase 22 introduces no context deletion endpoint.

## 5. Dates, lifecycle, concurrency, and retention

### Deadline semantics

| Mode | Accepted representation | Interpretation |
|---|---|---|
| No deadline | `due_kind=none`; all due fields null | No inferred due date |
| Date-only | `due_kind=date`, ISO calendar `due_date`, explicit IANA `due_timezone`; `due_at=null` | Due throughout that local calendar date; overdue once local current date is later |
| Timed | `due_kind=datetime`, aware RFC 3339 `due_at`, explicit IANA `due_timezone`; `due_date=null` | Normalize instant to UTC; retain zone for faithful display; overdue when server now exceeds instant |

Reject naive timed values, invalid zones, impossible dates, DST gaps and offset/zone mismatches. For an ambiguous repeated local time require the user to choose an offset; validate it against the zone. Date-only values must never round-trip through JavaScript `Date` or UTC midnight conversion. Use a browser zone only as an editable suggestion and persist the confirmed zone; the machine/session timezone is not a business default.

Treat AI `due_at`, relative expressions such as “next Friday,” and XLSX potential date strings as unconfirmed suggestions. The user must select a mode and resolve ambiguity. Missing source time/zone is not permission to guess. Due changes are explicit edits with events. Overdue is a computed property, not a scheduled status mutation; exclude completed, cancelled, and archived items from the default overdue list.

List filters must distinguish due-date ranges from timed instant ranges. Date-only overdue compares the server's current instant in each item's stored zone; never compare all dates to UTC's current date. For combined ordering, define a comparison instant as the next valid local-day boundary for date-only items, without storing a fake timed deadline. Validate difficult timezone/calendar boundary cases in PostgreSQL and Python. If efficient mixed-mode filtering proves too costly, ship separate date/time filters with explicit UX rather than silently wrong comparisons.

### Lifecycle and editing

Proposed transitions: `open ↔ in_progress`; either active state may become `completed` or `cancelled`; explicit reopen from either terminal state returns to `open`. Completion and cancellation timestamps are server-set. Reopen clears the current terminal timestamp while preserving prior events. Repeated requests to the already-current target can be no-ops without extra events; stale versions still receive conflict responses.

Recommend editing title, description, due information and context only while unarchived and open/in-progress. Terminal items must be reopened before changing business details. Archive/restore can apply in any status and preserve that status. Archived items are read-only except restore. There is no “execute,” “send,” “approve reply,” or “verified fulfilled” tracking operation.

Every mutation uses `id + user_id + expected_version`; increment version and append events atomically. This covers text edits as well as status races, unlike reusing only workflow expected-status checks. Domain methods validate transitions; repository conditional updates detect concurrent changes. A rejected/failed transaction must leave neither events nor partial source rows.

### Idempotency and deduplication

Require a stable client-generated `creation_key` per deliberate create attempt, retained across network retries. Store the server-normalized request digest with the item. Same user/key and same payload returns the existing owned resource; changed payload returns 409. Concurrent creates rely on a DB unique constraint and safe conflict recovery, not a pre-insert lookup alone. Do not confuse the existing per-request telemetry ID with this retry key.

For AI-confirmed creation, additionally derive `origin_candidate_key` from typed persisted analysis ID, allowlisted field, candidate index, and digest of the stored candidate. One user may create at most one item from that exact candidate in the first scope; a repeat with a new request key returns an owned conflict reference for review, without modifying the existing item. Existing completed/archived items still count. No generic “force” flag bypasses this rule. A deliberately distinct manual item remains possible and is clearly manual.

Reanalysis generates a new persisted analysis ID; semantically similar suggestions from different runs are not exact duplicates. Optional same-owner similarity warnings can be added later, but must not auto-merge or suppress user intent. No global content hashes or cross-user duplicate disclosures. Canonicalization rules, key limits (proposed maximum 128 characters), hashing algorithm and race outcomes must be locked in 22A and tested. Digests are sensitive metadata and are not logged.

Recommend retaining creation idempotency and candidate keys for the lifetime of the item. Source-analysis deletion or connector disconnect must not erase the confirmed item or its keys. An authenticated retry can return an already-created owned item even if its source is now missing; new creation must still validate currently available sources.

### Archive versus deletion

Recommend reversible archive, no item hard-delete API in the MVP. Account-level erasure remains a separate explicit administrative lifecycle, not a new Phase 22 feature. Archived content remains user data, so archive is not erasure. Operator approval is needed for this retention boundary and the event/source retention policy. No automatic retention jobs are proposed.

## 6. Confirmation, provenance, and provider contracts

Recommended flow:

1. A user opens an already persisted, owned communication or attachment analysis. Rendering it performs no mutation and no new AI call.
2. The user selects an existing candidate and opens “Create tracked action/obligation.” The form shows the source, AI/advisory label, truncation/warnings, and editable title/description, explicit kind, optional context, and unconfirmed due information. AI owner text is never mapped to a user or mailbox.
3. The final user gesture submits a versioned candidate locator plus reviewed fields and idempotency key. Cancelling creates nothing. No item is created on Analyze, render, suggestion selection, context association, or autosave.
4. The server reloads the owned persisted source, validates allowed field/index/digest and provenance, validates context and due inputs, derives owner and confirmation metadata, and atomically inserts the item, sources and real events.
5. Creation records only the final reviewed data. It neither creates a `WorkflowAction` nor grants approval/execution permissions. If a user subsequently wants to reply, the existing Analyze → Propose → Approve/Reject → Execute path remains required.

Candidate locators should allow communication/ordinary attachment `action_items`, and XLSX `potential_action_mentions` or `potential_dates`. They identify an observation, not a verified duty. A potential date alone requires the user to supply what is due. Multiple observations can be explicitly referenced but must not be automatically paired. Persisted candidates exceeding tracking text bounds require visible user editing; do not silently truncate business meaning.

An ephemeral/nonpersisted analysis can support manual typing, but cannot be represented as verified persisted AI provenance. Missing/deleted source or digest mismatch before first confirmation must fail safely and allow a separately chosen manual creation flow. Source detail links later resolve only through normal owned history/mailbox APIs; if the source is unavailable, show that fact without attempting to retrieve it automatically.

For direct communication references without an analysis, verify the owned connector and a nonempty opaque message ID; disclose that this is a user-supplied reference, not proof that the provider still has that message. Do not fetch content to strengthen that claim. For persisted attachment analysis, derive the entire connector/message/attachment tuple from its owned row. Disconnect does not prohibit reading already persisted analysis history; adding a mailbox reference still requires an existing owned connector, without requiring active credentials merely to store provenance.

**Provider recommendation: no contract or prompt changes in the first scope.** `AIProvider` already offers `analyze`, `suggest_business_context`, and `analyze_tabular`. Mock is deterministic/offline; Foundry and Bedrock adapt structured outputs through their existing parsing/validation paths. None needs to learn durable IDs or tracking mutations. A local deterministic projection of persisted observations supplies the confirmation form.

If a later approved requirement demands fresh structured obligation extraction or relationships absent from current outputs, introduce a separate bounded, advisory provider-neutral contract with fail-closed unsupported behavior, Mock support, Foundry/Bedrock parity tests, privacy limits and explicit invocation. Do not retrofit authoritative IDs/owners into `TabularAnalysisResult`, silently invoke models on tracking reads, or promise extraction from data excluded by bounded XLSX sampling.

## 7. API, authorization, errors, and logging

Proposed API namespace: `/api/v1/work-items`, explicitly separate from `/workflow-actions`. Final paths and permissions require 22A approval.

| Candidate endpoint | Capability recommendation | Required object checks |
|---|---|---|
| POST `/work-items` | authenticated analyze; additionally read when adding mailbox provenance | Server owner; owned active context if supplied; each supplied source independently validated |
| POST `/work-items/from-analysis` | authenticated analyze; additionally read for mailbox/attachment-backed source | Owned persisted source and valid candidate locator; derived provenance; owned active context |
| GET `/work-items`, GET `/work-items/{id}` | authenticated analyze | Owner in SQL; all filters remain owner-scoped |
| PATCH `/work-items/{id}` | authenticated analyze | Owned item + expected version; active editable state; owned active new context |
| POST `/{id}/status`, `/{id}/archive`, `/{id}/restore` under `/work-items` | authenticated analyze | Owned item + expected version + allowed transition |
| GET `/work-items/{id}/events` | authenticated analyze | Owned item; event owner scoped in SQL |
| Existing context timeline + proposed work-items context tab | existing authenticated analyze | Owned context, direct item association or recorded context event, and same-owner rows |

Reusing analyze follows Phase 20/history permission policy and avoids unnecessary identity-provider registration changes. It is nevertheless a product authorization decision: if independent task-only access or read-only collaborators are needed, new work-item permissions and a different access model require explicit approval. No use of `communications:workflow`/`send` is needed for tracking, and tracking grants neither. Requests containing mailbox provenance must require read+analyze even when the extra data is nested in a manual creation request. Enforce that on the server, not through button visibility.

Reject unknown owner, actor, timestamp, version-increment, execution target or authority fields using strict request schemas. Use the submitted expected version only as a concurrency condition. An application owner role does not widen item/context/source access. Do not use email, mailbox OAuth identity, AI owner strings, provider identities, cloud identities, or deployment identities as authorization keys. `AUTH_MODE=disabled` must not permit durable authenticated tracking APIs.

Proposed list filters: kind, status, archive visibility, current context (including unassociated), due mode/range, and overdue. Limit 20 by default, maximum 100; deterministic ordering with ID tie-breaker. Offset pagination is consistent with current APIs but can shift under concurrent inserts; document that property and do not present it as a stable snapshot. Never fetch all items in the browser to filter. Defer full-text search and totals until justified. Validate referenced context filters as owned and return 404 for unknown/foreign IDs, not counts that disclose existence.

Error behavior: 401 for missing/invalid authentication, 403 for missing capability, indistinguishable 404 for unknown/foreign objects, 409 for invalid lifecycle, stale version, archived target context, changed candidate or conflicting idempotency payload, 422 for malformed fields/dates, sanitized 503 for persistence unavailability. Reuse centralized exception handling and `ErrorResponse`; do not leak SQL, source data, or provider text. If machine-readable conflict codes are added, extend the shared optional code convention compatibly rather than matching English messages in the frontend.

Logs should contain operation, request correlation ID, safe internal item ID, event type, outcome/error class, counts and timing only. Exclude titles, descriptions, suggested owners, due text, provider message IDs, candidate values/digests, raw payloads, analysis results, workbook cells, tokens, prompts and raw provider responses. Error/validation logging must also obey this rule; field-level feedback must not echo entire input objects. Tracking services should not receive connector, parser, scanner, executor, credential resolver, or AI provider dependencies at all.

## 8. Timeline and frontend design

Keep the context timeline a read-only projection. Add work-item event types with IDs such as `work_item_event:<event_uuid>` and the actual server event timestamp. Do not use `due_at` as an event occurrence or infer an edit/completion from `updated_at`. A future deadline belongs in tracking/upcoming views, not as a claim that something happened.

Events belong to the context recorded at the time of the event. If an item created without a context is later associated, that context receives an association event at association time; do not backdate item creation into it. Moving A → B preserves earlier events under A, records disassociation under A and association under B, and places subsequent events under B. The current-items tab follows the current association. Historical event titles should be generic and link to the current owned item, not misleadingly display its present title as a historical title snapshot. This policy is a proposed extension to ADR-029 and requires approval.

Merge indexed, owner/context-scoped work-item event pages with existing timeline ordering (`occurred_at DESC`, deterministic ID tie-break). Add tie, pagination and duplicate-event tests. Do not persist fabricated legacy events or turn the timeline into a write path. If existing aggregate query costs prevent bounded acceptable behavior, make a focused timeline query improvement an explicit 22E acceptance requirement rather than silently capping and omitting history.

Frontend proposal: global “Tracking” list with filters and explicit manual create; detail/editor with due mode, timezone, status and archive controls; “Tracking” tab in a context; “Create tracked item” buttons in persisted communication, attachment and tabular results. Use consistent labels to distinguish “AI suggestion,” “tracked item,” and “reply workflow.” Do not label human-marked completion as verified compliance.

Reuse typed API modules, `EciApiClient`, React Query hooks, `PermissionGate`, confirmation-dialog and product-error patterns. New mutations invalidate list/detail/events and both old/new context views. Clear/cancel tracking queries and pending confirmation state on authenticated identity changes, extending `App.tsx` cache cleanup; reject late responses from a prior identity. Never persist tracking drafts or source text into browser storage by default. A user switching mailbox alone does not change application ownership, but stale mailbox-specific review forms must reset.

Include keyboard/focus behavior, screen-reader labels, empty/loading/error states, conflict recovery without silently overwriting edits, explicit retry using the same creation key, date-only rendering without timezone shifts, and displayed source-unavailable/truncated-analysis states. Source navigation must not auto-Analyze, auto-fetch attachment bytes, or auto-send.

## 9. Risk register

| Risk | Severity | Mitigation / release evidence |
|---|---|---|
| Tracking conflated with reply authorization | Critical | Separate aggregate, route namespace and service dependencies; completion never invokes executor; workflow regression tests |
| AI silently creates duties or chooses owners | Critical | Human-confirmation-only mutation; server owner and locator validation; no writes from analysis/render; injection/side-effect spies |
| Cross-user item/source/context exposure, including Platform Owner | Critical | Owner predicates on every repository query; nested reference checks; ordinary and owner-role adversarial matrix |
| Tracking bypasses attachment scanner/retrieves bytes | Critical | No content-capable dependencies; no-network spies on tracking/timeline; retain CLEAN-before-parser regressions |
| Ambiguous dates or false XLSX date/action pairing | High | Explicit due modes and zone; no inferred array relationships; DST/date-only tests and visible user review |
| Duplicate creation or lost edits under retries/races | High | Unique creation/candidate keys, expected version, atomic event transaction; real PostgreSQL concurrent tests |
| Source deleted or mailbox disconnected | Medium | Retain minimal verified provenance and confirmed item; unavailable-source UI; no automatic reacquisition |
| Invented or misleading timeline history | High | Real events and context-at-event policy; no due-date/updated-at fabrication; no legacy backfill |
| Unbounded timeline or overdue queries | Medium | SQL owner/context filters and indexes; representative-volume query tests; explicit performance gate |
| Sensitive data copied into history/logs | High | Minimal reviewed fields, no text snapshots in audit, bounded schemas, log sentinel tests, retention approval |
| UI identity switch exposes cached tracking data | High | Query cancellation/reset and late-response tests; no persistent browser drafts by default |
| Destructive migration/rollback | High | Additive tables; no AI backfill; downgrade refuses populated tracking data unless separately approved retention/export plan |
| Broad obligation scope expands into compliance/task engine | High | Approve MVP semantics first; recurrence, legal determinations, dependencies and automation deferred |
| Historical PASS treated as Phase 22 or live certification | Medium | Fresh local regression before release; cloud evidence separately authorized and accurately attributed |

## 10. Decisions and blocking conditions

### Constraints that can be carried forward immediately

These are already supported by the user instructions and accepted architecture, not new discretionary product decisions: separate tracking from `WorkflowAction`; verified internal ownership; no Platform Owner bypass; optional context; no AI-authoritative mutations; no auto-send or approval bypass; no attachment retrieval from tracking/context APIs; preserve scanner-before-parser and bounded `.xlsx`-only handling; reuse analysis stores for evidence; no raw-content duplication; no fabricated history; no historical AI backfill; preserve cloud identity separation and independent deployment authorization.

### Operator decisions required before implementation

| ID | Blocking decision | Recommendation to approve in 22A |
|---|---|---|
| B1 | Product/domain boundary | One `BusinessWorkItem` with action/obligation kind, zero/one due value; no standalone deadlines, recurrence, parent-child obligation/action graph or team assignment |
| B2 | Time and lifecycle semantics | Explicit date-only/timed modes and IANA zone; overdue rules; open/in_progress/completed/cancelled, explicit reopen, terminal-edit policy and separate archive |
| B3 | Authorization policy | Reuse authenticated analyze for tracking; add read for mailbox provenance; no new capability or owner bypass in MVP |
| B4 | Provenance, confirmation and duplication | Server-validated persisted candidate locators, bounded immutable initial sources, no provider changes, exact candidate uniqueness and lifetime creation-key retention |
| B5 | Context/history and concurrency | Optional direct context FK, recorded context-at-event history, explicit move policy, archived-context behavior, append-only minimal events and expected-version writes |
| B6 | Retention and delivery scope | Archive-only public lifecycle, source-deletion independence, user-erasure cascades, no destructive rollback with data; approve the selected frontend/filter scope and slices |

These six approval groups are the complete identified blockers to starting implementation on this baseline. They are product/architecture choices, not discovered defects requiring Phase 20/21 reopening. If any recommendation is rejected, revise the design and acceptance criteria before migrations. This assessment does not substitute for those decisions.

Fresh local tests, migration safety and performance evidence are subsequent release gates, not prerequisites to deciding 22A. Azure and AWS each require later independent authorization; none is needed to assess or implement locally. Phase 17D remains deferred unless the operator separately changes release scope. Provider live tests are unnecessary for a phase that leaves provider contracts unchanged.

## 11. Proposed implementation slices

All paths below are proposed unless they appear in the evidence map. Revision IDs are provisional and must be checked against the actual head when implementation is authorized. Each slice ends with a report; do not advance beyond the approved scope automatically.

### 22A — Architecture and product lock

- **Objective/scope:** Resolve B1–B6; lock model, due semantics, status transitions, API permission matrix, confirmation/deduplication, source-retention and timeline policy. Write the accepted ADR and Phase 22 roadmap; confirm first-release exclusions.
- **Dependencies:** This assessment and explicit operator authorization/decisions.
- **Expected files:** Proposed `docs/decisions/ADR-030-action-deadline-and-obligation-tracking.md` (verify number availability), decision index, `docs/roadmap/phase-22-action-deadline-obligation-tracking.md`, `docs/codex/reports/phase_22a_report.md`.
- **Migration:** None.
- **Security invariants:** Record all section 10 carried-forward constraints and the exact permission/ownership matrix.
- **Acceptance:** No unresolved schema-affecting approval; examples cover manual, AI-confirmed, date-only, source missing, cross-user and context-move cases.
- **Tests/checks:** Review examples against existing contracts; documentation links and `git diff --check`. No test execution implying database access needed.
- **Non-goals:** Domain code, schema, routes, frontend, provider calls, cloud access.

### 22B — Domain, persistence, and atomic history foundation

- **Objective/scope:** Implement work-item domain, due value validation, lifecycle, owned repository, conditional version updates, creation idempotency and event persistence. Add core fields/events now so no first-use history is lost. Internal services may be exercised by tests; no public route yet.
- **Dependencies:** Accepted 22A; local approved implementation environment.
- **Expected files:** `app/domain/models/business_work_item.py`, `app/domain/interfaces/business_work_item_repository.py`, `app/domain/enums.py`, domain exceptions; `app/infrastructure/storage/models.py`, `repositories/business_work_item.py`; domain and SQLAlchemy unit-of-work files; focused domain/repository/PostgreSQL tests and test UoW fixtures.
- **Migration:** Proposed `22b0001`, parent `21d0001`, creates work items and events with constraints/indexes; no existing-row backfill. Candidate/source-specific columns may wait for 22D as locked in 22A. Downgrade must refuse populated tracking tables by default.
- **Security invariants:** Server ownership, child ownership consistency, context validation, atomic rows/events, no content/provider/executor dependencies.
- **Acceptance:** Valid round-trip on SQLite and PostgreSQL, due checks enforced, illegal transitions rejected, same-owner SQL, one winner under concurrent versions and create keys, transaction rollback leaves no residue.
- **Tests:** Focused domain/repository tests, PostgreSQL constraints/concurrency/atomicity, upgrade from Phase 21 fixture preserving analysis data, safe downgrade empty/populated behavior; full backend because UoW is shared; ruff, pip check, diff check.
- **Non-goals:** AI confirmation, public endpoints, reminders, sending, cloud migrations.

### 22C — Manual tracking API and ownership

- **Objective/scope:** Manual create/get/list/update, due filters, lifecycle/archive/restore, event history, optional direct context association and explicit movement. Initial manual creation can have no source until 22D adds typed references.
- **Dependencies:** 22B.
- **Expected files:** `app/application/services/business_work_items.py`, application exceptions; `app/schemas/work_items.py`, `app/api/routes/work_items.py`, router/dependencies/main exception wiring; domain/repository query extensions; unit and API integration tests.
- **Migration:** None expected; use 22B schema. Any necessary additional index is a reviewed additive revision, not an edit to an applied migration.
- **Security invariants:** Authenticated analyze, owner-scoped reads/writes and context filters; version preconditions; no owner/actor injection; no external effects.
- **Acceptance:** Manual item works without mailbox/context; deterministic bounded filtering; correct overdue behavior; unknown/foreign 404 including Platform Owner; conflicts preserve saved state; idempotent retries.
- **Tests:** Authentication/permission matrix, invalid fields/timezones/DST, cross-user nested references, terminal/archive behavior, create/update races, missing persistence, privacy logs, spies proving zero AI/mailbox/scanner/executor calls; full backend and standard checks.
- **Non-goals:** Analysis conversion, frontend, task assignment, calendar or reminder jobs.

### 22D — Verified sources and human-confirmed creation

- **Objective/scope:** Typed provenance, bounded source references for manual creation, deterministic candidate projection from existing persisted analyses, explicit reviewed creation from communication/attachment/XLSX suggestions and candidate deduplication.
- **Dependencies:** 22C and accepted confirmation contract; no provider enhancement prerequisite.
- **Expected files:** `app/domain/models/business_work_item_source.py`; source repository interface/implementation; `app/application/services/work_item_confirmation.py`; work-item schemas/routes/service, UoW/models; tests for communication, ordinary attachment and XLSX sources.
- **Migration:** Proposed `22d0001`, parent 22B head, adds sources and confirmation/candidate fields not already in 22B; existing manually created items retain manual origin and no invented sources or confirmation events.
- **Security invariants:** Reload owned source; never trust AI IDs/owners/dates; read+analyze for mailbox provenance; source/creation/event atomicity; no bytes/provider invocation or workflow mutation.
- **Acceptance:** Rendering/cancelling creates zero records; one explicit confirmation creates exactly one item with verified minimal provenance; duplicate race produces one item; changed/missing source fails safely; deleted source after create does not invalidate tracking.
- **Tests:** Source type confusion, mismatched tuples, direct-text source, foreign source/context/connector, owner-role non-bypass, invalid index/digest, unbounded text, repeated/new analysis IDs, retries after source deletion, injection and truncation disclosures; PostgreSQL uniqueness/atomicity; retain Phase 21 side-effect and provider parity regressions offline.
- **Non-goals:** New AI extraction contracts, automatic date/action pairing, semantic auto-merge, source editing after create, historical backfill.

### 22E — Frontend and context timeline integration

- **Objective/scope:** Global tracking list/detail/editor, due controls and filters, status/archive controls, confirmation UI in existing persisted analysis panels, context tracking tab, real event timeline integration and identity-safe caches.
- **Dependencies:** 22C and 22D contracts.
- **Expected files:** `frontend/src/api/workItems.ts`, `api/client.ts`, `hooks/useWorkItems.ts`, `pages/WorkItemsListPage.tsx`, `pages/WorkItemDetailPage.tsx`, `components/workItems/`; mailbox analysis panels, `ContextWorkspacePage.tsx`, context types/copy/hooks, `App.tsx`, shell/navigation and product errors; `app/application/services/context_timeline.py`, event enums/schemas and repository queries; frontend and backend timeline tests.
- **Migration:** None expected; event indexes from 22B. Measured query findings may justify a separately reviewed additive index migration.
- **Security invariants:** Explicit final confirmation, no mutation on view, no automatic Analyze/send; server remains authority; no cross-identity cache leakage or raw-source browser persistence.
- **Acceptance:** Complete manual and confirmed user flows; context association independent of source message link; genuine timestamps across archive/reopen/context moves; paging/ties correct; accessible controls; visible timezone/AI uncertainty/source availability; stale edits recover without overwrite.
- **Tests:** React Testing Library/Vitest flows, keyboard/focus/accessibility, permissions, retry key reuse, date-only rendering/DST, cancelled modal no writes, identity switch and late response, cache invalidation for both contexts; backend timeline ordering/history/privacy/query-volume tests. Frontend typecheck, lint, full tests, production build; backend regression because timeline is shared.
- **Non-goals:** Calendar view, notifications, workflow execution controls inside tracking, invented legacy events, broad UI redesign.

### 22F — Local hardening and release readiness

- **Objective/scope:** Consolidate regressions, boundary attacks, representative-volume performance, migration/rollback rehearsal against disposable local databases, docs/API/runbooks and release evidence. Fix only Phase 22 defects found.
- **Dependencies:** 22B–E accepted; locally safe test database configured.
- **Expected files:** Phase 22 tests across `tests/unit`, `tests/integration`, `tests/postgres`, frontend tests; `tests/postgres/{conftest,alembic_checks}.py` inventory/head updates; CI changes only if required; architecture/API/runbooks, phase roadmap, `phase_22f_report.md`.
- **Migration:** No feature migration expected; rehearse full chain and data-preserving upgrade locally. Do not run a populated downgrade that discards tracking history.
- **Security invariants:** All above plus explicit evidence of no forbidden side effects and privacy-safe failures.
- **Acceptance:** All required local checks pass with counts, safe migration evidence, concurrency/atomicity and representative query behavior documented; no unresolved critical/high boundary defect; deployment artifacts/runbook reviewable before authorization.
- **Tests/checks:** Focused tests first, then full backend, real local PostgreSQL integration, `python -m ruff check .`, `python -m pip check`, `git diff --check`; frontend `npm run typecheck`, `npm run lint`, `npm run test -- --run`, `npm run build`. Provider tests use Mock/stubs only. Verify test DB is disposable/local before fixtures that upgrade/truncate it; existing PostgreSQL safety helpers must remain enabled.
- **Non-goals:** Azure/AWS access, paid models, live mailbox analysis, production migrations, broad Phase 17D verification.

### 22G — Optional, independently authorized cloud validation and closure

- **Objective/scope:** Only after separate authorization, deploy the accepted artifact/migrations to each named environment and validate tracking with approved identities and synthetic/minimal records. Treat Azure and AWS as separate operations and evidence sets.
- **Dependencies:** 22F PASS, explicit per-cloud access/deployment/migration scope and approved validation plan. Prior Phase 21 authorization does not carry into Phase 22.
- **Expected files:** Established deployment/migration runbooks if changes are necessary, `phase_22g_report.md`, final roadmap/closure documentation. No new cloud infrastructure presumed necessary.
- **Migration:** Apply the reviewed Phase 22 chain only after checking actual database revision and deployed artifact state; do not repeat a completed migration blindly. Retain existing Phase 21 data and use an approved backup/rollback plan.
- **Security invariants:** No IAM expansion, resource resize/delete/recreate, mailbox/attachment retrieval or paid AI calls unless independently and explicitly authorized for a concrete test. Tracking smoke tests should need none of those content/model calls.
- **Acceptance/tests:** Verify actual artifact identity, head, health, manual/confirmed tracking using approved persisted fixtures, isolation, due display, timeline and safe logs; record exactly what was exercised and which claims remain local-test evidence.
- **Non-goals:** New business automation, infrastructure redesign, sending messages, resuming Phase 17D or starting the next phase.

## 12. Completion and recommended next step

**Ready to begin architecture lock; not yet ready to begin implementation.** Resolve B1–B6 and explicitly authorize 22A. No technical blocker was found that requires replacing existing identity, mailbox, provider, attachment or context architecture. The proposed event journal, time semantics and confirmation/idempotency design are new Phase 22 decisions and must not be treated as already accepted ADRs.

Recommend a **fresh Codex session** for 22A/implementation after the operator decisions, with this report, repository `AGENTS.md`, the accepted ADRs and the exact approved slice supplied as the handoff. Recheck branch/HEAD/worktree and migration head there. A fresh session provides a clear authorization boundary and room for implementation/testing; it does not require repeating the assessment or changing sessions for technical reasons.

Assessment change inventory: created `docs/codex/reports/phase_22_readiness_assessment.md`; no existing files modified. Pre-existing untracked `AGENTS.md` preserved. Migration changes: none. Application tests run: **0**, intentionally, for this documentation-only assessment; historical counts are attributed in section 1. Report-only validation: whitespace/link checks and final worktree inspection. Cloud resources accessed or modified: **none**. Known limitations: no live database/cloud/CI re-verification; no fresh runtime or performance certification; six approval groups remain open. Assessment ends here.
