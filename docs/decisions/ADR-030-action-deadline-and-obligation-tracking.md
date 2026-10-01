# ADR-030: Action, Deadline and Obligation Tracking

## Status and authority

**Accepted — architecture lock, not implemented.** Date: 2026-09-26. Phase 22A.

The operator explicitly approved all six decision groups B1–B6 from the [readiness assessment](../codex/reports/phase_22_readiness_assessment.md). They are settled decisions, not outstanding approval requests. This ADR makes their implementation contract concrete. The assessment is preserved as historical evidence; its earlier unresolved-decision language is superseded by this acceptance, not edited away.

Baseline: `master`, `bfc68b0cbb052d2e2656a7804dfcbd5f88150a77`; repository migration head `21d0001` (parent `20c0001`). ADR-030 was available. Phase 20 and Phase 21 remain CLOSED / PASS; Phase 17D remains deferred. This document authorizes no implementation, migration execution, commit, push or cloud operation. Each later slice requires explicit authorization.

## Context and motivation

ECI persists analyses, attachment analyses, approval-gated reply workflows and optional BusinessContexts. AI action suggestions have no independent tracking lifecycle. Users need to deliberately record a business action or commitment, track its due information and status, and retain minimal provenance after the source disappears.

| Concept | Meaning and authority | Phase 22 boundary |
|---|---|---|
| `ActionItem` | Advisory analysis output: description, optional free-text owner, due suggestion and priority | Remains analysis JSON; neither an authorized assignment nor a confirmed deadline |
| `WorkflowAction` | Owned reply proposal, approval snapshot and controlled external execution | Existing `pending → approved/rejected`, `approved → executing`, `executing → executed/failed` state machine remains unchanged |
| `BusinessWorkItem` | New durable, user-confirmed tracking aggregate | Records business intent and human status declarations; never sends or executes a reply |

Application identity, mailbox identity, cloud workload identity, database identity and deployment identity remain separate. Existing Analyze → Propose → Approve/Reject → Execute remains the only established reply workflow. Tracking is not an alternative approval path.

## Accepted decision inventory

| Group | Accepted decision |
|---|---|
| B1 — Product/domain | Separate `BusinessWorkItem`; immutable `action` or `obligation`; one lifecycle; zero/one due value; zero/one direct context; bounded sources; single-user tracking |
| B2 — Dates/lifecycle | Explicit none/date-only/datetime modes and confirmed IANA zone; computed overdue; open/in_progress/completed/cancelled; explicit reopen; terminal edit restriction; separate archive/restore |
| B3 — Authorization | Authenticated `communications:analyze`; additionally `communications:read` for creation/confirmation with mailbox provenance; internal ownership everywhere; no new capability or owner bypass |
| B4 — Confirmation/provenance | Manual or explicit persisted-analysis confirmation; deterministic candidates; bounded verified references; creation idempotency and exact-candidate uniqueness; no provider changes |
| B5 — Context/history | Optional direct association; atomic append-only minimal events; real timestamps and context-at-event; expected-version mutations; archived-context rules; read-only scoped timeline |
| B6 — Retention/delivery | Reversible archive, no public hard delete, account erasure respected; complete tracking UI and history; independently authorized cloud validation |

## Aggregate and typed due value

Domain root: `BusinessWorkItem`, with `owner_user_id` mapped to SQL `user_id`, matching the existing context/workflow convention. Domain enums use `StrEnum`; SQL uses constrained text, not PostgreSQL ENUM. Kind is immutable. Title is trimmed, nonblank, 1–200 characters. Optional description is trimmed, blank becomes null, maximum 4,000 characters. This is the user's confirmed business content, not a place to copy raw source material.

API/domain `due` is a discriminated value. SQL stores the corresponding flat fields:

| API `due.kind` / SQL `due_kind` | Required value | Required null fields | Interpretation |
|---|---|---|---|
| `none` | No other due properties | `due_date`, `due_at`, `due_timezone` | No deadline |
| `date` | `date` as ISO `YYYY-MM-DD`, `timezone` as confirmed IANA zone | `due_at` | Due throughout that local calendar date |
| `datetime` | `at` as aware RFC 3339, `timezone` as confirmed IANA zone | `due_date` | Due at an instant; store UTC, retain confirmed zone |

`date` is the wire enum for date-only. Reject unknown/extra due properties, impossible dates, empty/unknown zones, zone strings over 64 characters, naive times, nonexistent DST wall times and offset/zone mismatches. For repeated local times, the user must explicitly select an offset that round-trips through the zone. The offset in the submitted RFC 3339 value disambiguates the occurrence; no silent first/second occurrence choice. Browser timezone is only an editable suggestion. Do not auto-confirm AI due values or resolve relative dates by guessing.

Use calendar-date values end to end; never convert date-only values to midnight UTC or through JavaScript `Date`. At one server reference instant per response, date-only overdue means the current local date in the stored zone is greater than `due_date`; timed overdue means now is strictly later than `due_at`. Only unarchived active items are overdue. Overdue is returned/computed, never a lifecycle column or scheduled mutation. Date-only comparisons need no invented timestamp, even across skipped calendar days. Test unusual IANA transitions as well as ordinary DST.

## Lifecycle and concurrency

Creation always sets `open`, version 1 and no terminal/archive timestamps. A client cannot create a terminal item.

| Current status (unarchived) | `open` target | `in_progress` target | `completed` target | `cancelled` target |
|---|---|---|---|---|
| `open` | No-op | Allowed | Allowed | Allowed |
| `in_progress` | Allowed | No-op | Allowed | Allowed |
| `completed` | Explicit reopen | Rejected | No-op | Rejected |
| `cancelled` | Explicit reopen | Rejected | Rejected | No-op |

A terminal-to-open request requires `reopen=true`; this flag is invalid for other transitions. Business fields (title, description, due, context) can be edited only while unarchived and active (`open` or `in_progress`). Terminal items must first reopen. Archive is permitted in any status and preserves it. Archived items permit only restore; repeated archive can acknowledge the existing archive as a no-op. Restore of an unarchived item is a no-op. No-ops must still pass ownership and expected-version checks and append no event.

`completed_at` is non-null iff status is completed; `cancelled_at` is non-null iff status is cancelled. All other combinations are rejected. Reopen clears current terminal timestamps; previous transitions remain in events. Archive sets `archived_at`, restore clears it. Timestamps are server-managed aware UTC. Completion is a human declaration, not independent or legal proof of fulfillment.

Every existing-item mutation requires positive `expected_version`. The repository writes with `WHERE id AND user_id AND version = expected_version`; one actual mutation increments version once, sets `updated_at`, and appends its events in the same transaction. Stale version is 409 even for an otherwise identical no-op. An ownership miss is 404. No field other than `expected_version` lets clients control version or server timestamps. Failed writes/commits leave neither partial sources nor orphan events. Repositories do not commit; the application unit of work commits once.

## Planned schema: all present in 22B

**One proposed migration: `22b0001`, revising actual head `21d0001`.** Recheck availability and head before implementing. Create all three tables, every field below, constraints and indexes in 22B. **No `22d0001` and no deferred source/candidate columns are planned.** 22D adds verification and confirmation behavior using this schema. Early source schema availability does not expose source APIs in 22B/C. This resolves the assessment's optional migration split and avoids rewriting existing items in 22D.

### `business_work_items`

| Fields | Types, nullability and constraints |
|---|---|
| `id`, `user_id` | Non-null UUID PK; owner FK to `users.id ON DELETE CASCADE`; unique `(id, user_id)` for child FKs |
| `kind`, `status` | Non-null text checks `action/obligation` and `open/in_progress/completed/cancelled`; status default `open` |
| `title`, `description` | Non-null text title length 1–200 after trim; nullable text description length 1–4,000 when present |
| `business_context_id` | Nullable UUID FK to `business_contexts.id ON DELETE SET NULL`; never cascade item deletion |
| `due_kind` | Non-null text check `none/date/datetime`, default `none` |
| `due_date`, `due_at`, `due_timezone` | Nullable SQL DATE, timezone-aware timestamp, text up to 64 characters; explicit null/non-null checks for the three modes above |
| `completed_at`, `cancelled_at`, `archived_at` | Nullable timezone-aware timestamps; terminal status pairing checks; archive independent of status |
| `created_at`, `updated_at` | Non-null server timestamps; `updated_at >= created_at`; present terminal/archive timestamps cannot precede creation |
| `version` | Non-null integer, default 1, check `>= 1` |
| `creation_origin` | Non-null text `manual/ai_confirmed`; no client-write field |
| `confirmed_by_user_id`, `confirmed_at` | Nullable UUID and timestamp; both absent for manual, both present for ai_confirmed; actor equals `user_id`, time cannot precede creation |
| `creation_key`, `creation_request_hash` | Non-null text; key 1–128 ASCII characters from `[A-Za-z0-9._~-]`; lowercase SHA-256 hex digest length 64; unique `(user_id, creation_key)` |
| `origin_candidate_key` | Nullable lowercase SHA-256 hex digest length 64; null for manual, required for ai_confirmed; unique `(user_id, origin_candidate_key)` (multiple nulls allowed) |

Use explicit SQL `IS NULL` / `IS NOT NULL` branches in checks so SQL UNKNOWN cannot permit invalid combinations. Domain validators additionally enforce IANA semantics, immutable identity/kind/origin/keys, normalization and precise payload shapes; timezone-database validation is not a portable SQL check. Existing SQLite handling must preserve/reconstitute UTC timestamps as in other repositories.

Initial indexes (in addition to PK/unique indexes): `(user_id, created_at, id)`, `(user_id, status, due_at, id)`, `(user_id, status, due_date, id)`, `(user_id, business_context_id, created_at, id)`. Query-plan testing may justify later additive indexes; no destructive schema rewrite.

Context existence is enforced by the FK; **same-owner context is enforced by the service/repository**, not implied by that FK. Before assigning a new context, load it by `id + user_id`, acquire a row lock and recheck active status inside the mutation transaction. Keep the lock through commit, serializing against existing context UPDATE/archive writes. Context ownership is immutable. Do not introduce an unsafe composite SET NULL that would null the item's owner, or add sharing/ownership changes to contexts. SQLite tests cover semantics; PostgreSQL tests must prove archive/association races.

### `business_work_item_sources`

| Fields | Types and rules |
|---|---|
| `id`, `work_item_id`, `user_id` | Non-null UUID PK and composite child FK `(work_item_id,user_id)` to `(id,user_id) ON DELETE CASCADE` |
| `source_kind` | Non-null constrained text: `communication`, `communication_analysis`, `attachment_analysis` |
| `analysis_id`, `attachment_analysis_id` | Nullable UUID opaque references; no FK to history tables |
| `connector_account_id`, `provider_message_id`, `provider_attachment_id` | Nullable UUID/text opaque provenance; nonempty provider IDs bounded to 2,048 characters each; preserve case and exact value, reject whitespace-only IDs |
| `candidate_field`, `candidate_index`, `candidate_digest` | Nullable allowlisted field text, nonnegative integer and lowercase 64-character SHA-256 digest; all present or all absent |
| `source_key`, `linked_at` | Non-null 64-character SHA-256 canonical reference digest and server UTC timestamp; unique `(work_item_id,source_key)` |

Typed checks: `communication` has connector/message, no analysis IDs, no attachment ID and no candidate locator. `communication_analysis` has only `analysis_id`; connector/message must be both absent or both present; attachment ID absent; locator may be absent or `action_items`. `attachment_analysis` has only `attachment_analysis_id` and requires the full connector/message/attachment tuple; locator may be absent or one of `action_items`, `potential_action_mentions`, `potential_dates`. XLSX versus ordinary attachment field applicability is checked against the loaded owned row, not inferred from client data. No source can claim both analysis types.

Maximum ten distinct sources per item, enforced by bounded creation input/domain validation; later source additions, editing and merging are not supported. Manual creation defaults to zero sources and may explicitly supply up to ten from 22D. AI confirmation requires its origin source and may include up to nine additional explicit sources. Sources are inserted atomically with creation; there is no later source-write endpoint. A source key hashes its typed identifiers and optional candidate locator, so two explicit observations in the same analysis may be distinguished. Reject duplicate canonical sources within a request.

Source ownership is verified through owned repositories before insert; no database FK can enforce ownership of opaque/deletable source references. Analysis-derived tuples come from the server. Direct communication references verify an existing owned connector and a supplied opaque message ID, with no claim of verified provider-message existence. No communication table is introduced. Existing owned disconnected connectors are acceptable for provenance: credentials or live provider reachability are not required. A missing connector prevents a new mailbox-backed link; it does not invalidate an already created item.

### `business_work_item_events`

| Fields | Types and rules |
|---|---|
| `id`, `work_item_id`, `user_id` | Non-null UUID PK and composite child FK to owned item, `ON DELETE CASCADE` |
| `actor_user_id` | Non-null UUID; check equality with `user_id` |
| `event_type` | Non-null constrained text: `created`, `edited`, `status_changed`, `archived`, `restored`, `context_associated`, `context_disassociated` |
| `occurred_at`, `item_version`, `event_ordinal` | Non-null server UTC timestamp, positive resulting version, nonnegative integer ordinal; unique `(work_item_id,item_version,event_ordinal)` |
| `context_at_event_id` | Nullable opaque UUID; no deletion-cascading context FK; owner validated when recorded |
| `metadata` | Non-null portable JSON/JSONB, default `{}`; allowlisted typed payload, maximum 8 KiB canonical UTF-8 enforced in domain/service |

Metadata holds only changed-field names, old/new typed due values, old/new status, and from/to context IDs as applicable. `created` records initial status/due and origin classification; `edited` lists changed title/description/due fields and old/new due only when changed; `status_changed` records both statuses; archive/restore need no text payload. Context events record from/to IDs. Never retain previous title/description text, source contents, full snapshots or arbitrary client JSON. SQL constrains scalar enums, ownership, version and uniqueness; the domain validates event-specific JSON structure/size.

Events are append-only through the application repository: no update/delete/event-create API. Account erasure cascades are the exception to retention. This is an audit journal, not event sourcing. Add indexes `(user_id,work_item_id,occurred_at,id)` and `(user_id,context_at_event_id,occurred_at,id)` in 22B. Per-item history uses `item_version ASC, event_ordinal ASC, id ASC` so transaction order remains clear even if clocks tie; the unique version/ordinal index supports this. Timeline projection retains existing `occurred_at DESC, id ASC`, using `work_item_event:<event_uuid>` as stable identity.

Cross-row guarantees (source bounds, ai-confirmed origin source existence, event coverage, validated context/source owner) belong to the aggregate transaction/repository contract, with rollback and direct-constraint tests. Do not imply SQL CHECK constraints can validate other tables. Account erasure must remove items and both child tables via the owner/parent cascades, including ORM deletion paths; no new account-erasure endpoint is introduced.

## Human confirmation, deterministic candidates and idempotency

Candidate projection reads existing owned persisted results only. Version-1 locators contain `projection_version=1`, `source_kind` (`communication_analysis` or `attachment_analysis`), `source_id`, allowlisted `field`, zero-based `index`, and `digest`. Communication and ordinary attachment analyses allow `action_items`; XLSX permits separate `potential_action_mentions` and `potential_dates` from `tabular_result`. Do not combine those arrays by index. Potential amounts are not tracking candidates. A date observation requires the user to supply what is due.

Projection is deterministic and read-only. It carries original advisory/truncation/warning disclosures, not invented relationships or verified deadlines. Server confirmation reloads the owned row, validates projection version, source type, field/index/digest, verifies derived mailbox provenance, and validates the user's final kind/text/due/context. AI owner text is display-only and never mapped to an internal owner. No item is created by Analyze, rendering, selection, autosave, context linking or cancellation of a review form. A final explicit confirmation submits `confirmed=true`; the server binds actor/time. Manual creation is also an explicit user submission. Ephemeral analysis can be manually transcribed but cannot claim verified persisted-analysis provenance.

Canonicalization version 1 is a documented shared pure function: UTF-8 JSON, object keys sorted lexicographically, compact separators, Unicode retained without case folding/normalization, no NaN/infinity; retain array order unless specified below. Hash with SHA-256 to lowercase hex. Candidate digest covers the **stored candidate JSON value**, including its existing optional values; it performs no guessed date conversion. The server-derived `origin_candidate_key` hashes `{projection_version,source_kind,source_id,field,index,digest}` with UUIDs in standard lowercase form. Reanalysis with a different persisted ID is a different candidate. Only the designated origin candidate is subject to item-level exact-candidate uniqueness; additional evidence references do not auto-merge items.

Creation request digest hashes the versioned normalized intent: route origin (`manual` or `ai_confirmed`), trimmed title/description, kind, due, explicit context/null, typed requested sources and origin locator/confirmation for conversion. Expand defaults, use canonical UUIDs, keep opaque provider IDs exact, normalize validated timed due values to UTC `Z` with six fractional digits, preserve date-only strings and the confirmed zone, and sort the source set by canonical JSON. Exclude creation key, server-generated IDs/times/actor and any source data loaded later. This allows deterministic replay after source deletion. Reject malformed/unknown fields before hashing; never silently truncate. Stable client-generated `creation_key` is supplied in the JSON body, retained across retries and never substituted by telemetry request ID.

| Situation | Required outcome |
|---|---|
| New valid key and source candidate | Atomic item + sources + events; 201 |
| Same owner/key and same digest | 200 with current owned item, no events or overwrites; source may now be unavailable |
| Same owner/key and different digest | 409 `work_item_creation_key_conflict` |
| New key for an already used exact candidate | 409 `work_item_candidate_already_tracked`, owned item Location reference; no change to existing item |
| Candidate changed before first confirmation | 409 `work_item_candidate_changed` |
| Source/connector absent or foreign before first confirmation | Indistinguishable 404 |

On replay, authenticate and enforce analyze plus read if the stored creation involved mailbox provenance; use preserved source rows to enforce that gate even after source deletion. Replays do not require the old context to remain active or source to remain present. Do not revalidate current-source availability before identifying a valid existing creation. Fresh requests still validate all references. Same-key replay takes precedence over candidate conflict. Lifetime unique keys include completed/archived items. New-key candidate conflict after source deletion may still return the owned conflict reference from preserved locator identity; it cannot create a new item without a currently valid source. No force bypass or semantic auto-merge; a deliberately distinct manual item is possible.

Database unique constraints are authoritative under concurrent requests. Use savepoints or transaction rollback and a fresh owner-scoped lookup after a unique conflict; never continue querying an aborted PostgreSQL transaction or convert all integrity errors into duplicate success. No loser events/sources survive. Lost-response retries of other mutations may return stale-version 409; the UI reloads rather than overwriting. Creation and candidate keys never rotate or expire while the item exists.

## Authorization and API contract

Locked namespace: **`/api/v1/work-items`**. `/api/v1/workflow-actions` remains separate and unchanged. No workflow executor/provider/content-capable connector, parser, scanner or credential resolver belongs in tracking services; database connector-account metadata repositories are permitted for ownership validation.

All operations require verified authentication and `communications:analyze`, including when development analyze otherwise allows `AUTH_MODE=disabled`. Map verified `(iss, sub)` through `IdentityResolver` to internal `users.id`. Platform Owner has no ownership exception. No new IdP scopes or work-item-specific capabilities. Email, mailbox/connector identity, AI owner text and cloud identity never authorize access. Read/workflow/send permissions do not imply analyze; analyze does not grant reply approval, execution or Send.

Paths below are relative to the locked namespace. `A` means authenticated analyze; `R` means additional communications:read. Conditional R is enforced server-side from every nested source and the loaded source record, never from a trusted client flag.

| Method/path | Request and success response | Permission and ownership |
|---|---|---|
| POST root | `{creation_key,kind,title,description?,due?,business_context_id?,sources?}`; 201 item, or 200 replay; Location header | A; +R for any mailbox-backed source; active owned context and each source/connector |
| POST `/from-analysis` | Manual business fields plus `candidate`, `confirmed:true`, optional additional sources; 201/200 item, Location | A; +R for mailbox-backed source(s); reload owned persisted candidate; no client-derived ownership/tuple |
| GET `/candidates` | `source_kind`, `source_id`, limit/offset; 200 `{items,limit,offset}` with locators/advisory disclosures | A; stored history only, same policy as owned analysis reads; no creation or provider access |
| GET root | Filters below; 200 `{items,limit,offset}` | A; owner in SQL; validate any context filter by ownership |
| GET `/{id}` | 200 item plus bounded sources and source availability | A; owned item; source resolution remains owner-scoped, no live fetch |
| PATCH `/{id}` | `{expected_version,title?,description?,due?,business_context_id?}`; 200 updated item | A; active unarchived owned item; explicit context change validates new active owned context |
| POST `/{id}/status` | `{expected_version,status,reopen?}`; 200 item | A; owned item, transition matrix and archive gate |
| POST `/{id}/archive` | `{expected_version}`; 200 item | A; owned item |
| POST `/{id}/restore` | `{expected_version}`; 200 item | A; owned item |
| GET `/{id}/events` | limit/offset; 200 `{items,limit,offset}` | A; owned item and owner-scoped events |
| Existing GET `/api/v1/contexts/{context_id}/timeline` | Existing page contract extended with real work-item event types in 22E | A; currently owned context, owner/context-scoped event query |

Candidate projection needs only A because it reads stored history; final mailbox-backed creation requires A+R. The context Tracking tab uses GET work-items with a current-context filter; no second tracking API namespace. A direct-text owned analysis without mailbox provenance needs only A for confirmation.

Creation defaults: `due={kind:none}`, description/context null, empty sources, open status. Manual sources become available in 22D; 22C rejects nonempty sources explicitly. PATCH omission means unchanged; null clears description/context; due must be replaced with a complete discriminated object (use `kind:none` to clear). Kind, sources, origin, owner, actor, creation/candidate keys, timestamps and incremented version are immutable/not accepted as patch fields. Reject unknown authority/execution fields. An empty or unchanged patch is a no-op only after normal version/editability checks.

Item responses include ID, kind, title/description, due, current context, status, lifecycle/archive/creation/update times, version, creation origin, confirmed time and computed overdue. No key/digest/internal actor metadata is needed in public responses; source locators are returned only where needed for candidate review. List entries omit source collections; detail resolves source availability from owned persisted metadata only. Missing sources render unavailable without discarding the item. Event responses omit business text snapshots and internal owner identities.

Filters: kind; one status; `archive=active|archived|all` (default active); current `business_context_id` or mutually exclusive `unassociated=true`; due kind; inclusive ISO `due_date_from/to` for date mode; inclusive aware `due_at_from/to` for datetime mode; `overdue=true|false`. Range mode must match due kind (or determines it if omitted); mixed ranges, reversed bounds and contradictory modes return 422. Default sort `created_at DESC,id DESC`. Optional `sort=due_asc` requires an explicit date or datetime mode, sorts that typed value ASC then ID ASC; no mixed-mode artificial deadline ordering. Date-only overdue filters compare per-item zones at a single server instant before pagination, not browser filtering or UTC-calendar comparison. If SQL implementation requires a zone-aware expression, validate it against the domain predicate in PostgreSQL. Response `overdue=false` includes non-overdue terminal/archived items when their filters allow them.

List, candidates and events default limit 20, max 100, nonnegative offset; reject invalid bounds. Offset pages are deterministic for unchanged data, not snapshot-consistent across concurrent changes. No totals, full-text search or browser-wide fetch/filter in the MVP. Unmapped authenticated users get an empty global list; object/context/source lookups return 404; creation resolves/creates the internal user through the existing identity service.

Reuse centralized `ErrorResponse` and optional machine-readable `code`: 401 missing/invalid authentication, 403 missing capability, indistinguishable 404 unknown/foreign references, 409 invalid state (`work_item_invalid_transition`/`work_item_not_editable`), stale version (`work_item_version_conflict`), archived new context (`work_item_context_archived`) or creation/candidate conflicts above, 422 malformed inputs, sanitized 503 persistence unavailable. Duplicate-candidate conflict exposes only an owned Location reference, avoiding a general shared-error body redesign. Do not reveal foreign existence via conflict details. Validation failures must not echo raw submitted objects into logs.

## Business Context and event history

Current association is optional and direct. Communication context membership neither grants access nor sets work-item membership; item creation never auto-links a communication. Context move is a versioned business edit and thus requires active, unarchived item status. Existing items under an archived context can progress, edit business details, archive/restore or detach; a terminal item must reopen before any business edit/detachment. No new association to an archived context. Context archive does not change item status or archive state.

| Mutation | Events and context-at-event |
|---|---|
| Create without/with context | `created` ordinal 0 under null/current context; no invented earlier association |
| Edit details/due | `edited` under context at the start of the mutation |
| Status/archive/restore | Corresponding event under current context, even if context archived |
| Attach previously unassociated item | `context_associated` under target at actual attach time; never backdated creation |
| Detach | `context_disassociated` under old context |
| Move A → B | `context_disassociated` under A then `context_associated` under B, same resulting version and timestamp, increasing ordinals |
| Edit plus move in one PATCH | `edited` under old context first if details changed, then association events; one version increment |

Use one server timestamp per mutation and ordinals starting at 0 for its event sequence. History under A remains under A after moving to B; subsequent events belong to B. The current Tracking tab follows current association. Generic historical titles link to the current owned item without pretending its present title was its historical title. Removing source communication links does not remove item events.

The context timeline remains a read-only projection; new event queries filter owner/context in SQL and use indexes. Preserve its existing timestamp/ID ordering with correct merged pagination and no silent truncation. Never infer events from `updated_at`, due dates, prior analyses, archive restoration guesses or legacy context data. Existing Phase 20 owner-wide analysis/workflow scans are a known performance risk; 22E must measure the merged path and make any necessary focused query correction explicit rather than add another owner-wide scan. Do not retrofit an event journal for legacy contexts.

## Retention, migration safety and privacy

Archive is reversible, not erasure. No public item hard-delete endpoint. Keep minimal sources, creation/candidate keys and genuine events for the item's lifetime. Analysis deletion, connector disconnect or disappearance of provider data cannot invalidate a confirmed item. Historical source/context IDs have no deletion-cascading FKs; current context deletion would set item context null, never transfer old history to a new context. No context deletion feature is introduced.

Account-level erasure retains existing user-deletion semantics: owned items cascade with users; their sources/events cascade with items, leaving no ownerless data. New tables are additive; no updates/backfill of historical AI output or Phase 20/21 rows. A 22B downgrade checks **all three tables before any DDL** and refuses if any tracking data exists. Do not discard data to force rollback; use roll-forward or a separately approved retention/export/rollback plan. Empty-table downgrade drops children before items. Cloud deployment must independently verify actual revision/artifact before applying an authorized migration.

Do not persist raw communications, workbook bytes/cells, extraction snapshots, prompts or provider responses. Logs allow operation, correlation ID, safe internal item ID, event type, outcome/error class, counts and duration only; omit titles/descriptions, due input text, provider IDs, candidate values/digests, request payloads and secrets. Keep scanner-before-parser, bounded `openpyxl`, `.xlsx`-only spreadsheet support, inert formulas and no external workbook network resolution unchanged. Tracking/context/candidate/history APIs retrieve no attachment bytes or mailbox content.

## Delivery and exclusions

The first release includes global Tracking list, manual create, detail/editor, due controls and filters, lifecycle/archive management, explicit creation from persisted communication/attachment/XLSX observations, optional context association, Business Context Tracking tab and genuine event/timeline history. Typed API clients and React Query/permission/error patterns are reused. Cancel/clear queries and pending confirmation on identity changes; discard late responses from a prior identity. Reset mailbox-specific forms on mailbox change. No browser persistence of business drafts/source text by default. Provide accessible confirmation, visible zone/date-only semantics, unavailable-source and truncated-analysis disclosures, and stale-version recovery.

Excluded: cross-user assignment/sharing/teams; recurrence; standalone milestones/deadline aggregates; parent-child graphs; multiple deadlines per item; notifications/reminders/escalation; calendar or external task synchronization; automatic tracking/compliance determinations; automatic replies/Send; automatic workflow linkage/completion; new AI extraction/provider prompts/contracts. Mock, Microsoft Foundry and Amazon Bedrock contracts stay unchanged. Phase 17D and later phases are not added to this scope.

## Alternatives and consequences

- Extending `WorkflowAction` is rejected: reply authorization and external side-effect reconciliation cannot represent editable human tracking.
- Separate action, obligation and deadline aggregates are rejected for this MVP: they introduce relationships/multiple lifecycles absent from approved scope.
- More JSON inside analyses is rejected: tracking must outlive source deletion and have independent concurrency/ownership/status.
- Automatic AI persistence or date/action array pairing is rejected: observation is not business confirmation.
- New capabilities and team ACLs are deferred: accepted permission reuse is sufficient for the single-user release but not a future task-only collaborator model.
- Sources/confirmation columns in a separate 22D migration are rejected: the accepted design is known now, so all three tables in 22B avoid schema churn and missing early history.
- Full event sourcing or raw-content history is rejected: the item remains authoritative and the journal minimal.

Benefits are a bounded new aggregate, preserved identity/attachment/workflow boundaries and a complete persistence contract before APIs. Costs include retained archive data, exact-candidate restrictions even after completion, explicit conflict recovery, timezone-sensitive filtering and a new atomic journal. These costs are accepted; performance, concurrency and privacy remain implementation acceptance gates, not reopened B1–B6 decisions.

## References and implementation boundary

- [ADR-029: Business Context](ADR-029-business-context-foundation-and-provenance-association.md)
- [ADR-013: identity and owned data](ADR-013-external-identity-mapping-and-user-owned-data.md)
- [ADR-015: approval-gated workflow](ADR-015-approval-gated-workflow-actions.md)
- [ADR-016: workflow persistence/provenance](ADR-016-workflow-persistence-and-analysis-provenance.md)
- [ADR-018: execution provenance](ADR-018-workflow-execution-target-provenance.md)
- [ADR-024: mailbox authorization boundary](ADR-024-connected-mailbox-read-and-analysis-authorization-boundary.md)
- [ADR-028: Platform Owner](ADR-028-platform-owner-identity-and-application-rbac.md)
- [Phase 20 roadmap](../roadmap/phase-20-business-context-matter-intelligence.md)
- [Phase 21 roadmap](../roadmap/phase-21-xlsx-tabular-intelligence.md)
- [Phase 22 readiness assessment](../codex/reports/phase_22_readiness_assessment.md)
- [Phase 22 roadmap](../roadmap/phase-22-action-deadline-obligation-tracking.md)
- [Phase 22A report](../codex/reports/phase_22a_report.md)

22A ends with documentation acceptance only. 22B may begin only after explicit operator instruction; local runtime acceptance and independent Azure/AWS validation are later gates.
