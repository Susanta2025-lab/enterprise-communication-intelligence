# Phase 15 — Browser Frontend

## Objective

Introduce a same-repository browser SPA for ECI application login and later product UX, without changing the established FastAPI bearer-token architecture or moving mailbox OAuth into the browser.

```text
Browser
→ React + TypeScript + Vite SPA
→ MSAL public client
→ ECI bearer access token
→ FastAPI protected API
```

Mailbox OAuth remains server-side and separate from ECI login.

## Status

Phase 15 is **In progress**. **15A, 15B, 15C, 15D, 15E, and 15F are Completed.** Phase 15G is next.

- **15A is Completed:** frontend foundation, MSAL browser authentication, typed API client, protected analyses smoke contract, explicit CORS allowlist, ADR-025. Live Entra SPA registration and real browser sign-in were not performed.
- **15B is Completed:** owned connector-account dashboard, Gmail/Microsoft Graph connect and exact-account reauthorize UX, disconnect confirmation, optional `FRONTEND_OAUTH_RETURN_URL` callback return, sanitized OAuth return handling in the SPA. Mailbox OAuth remains server-side. Live provider OAuth and Entra SPA registration were not performed.
- **15C is Completed:** connected-mailbox workspace for ACTIVE Gmail and Microsoft Outlook connectors, bounded first-page load (`page_size=10`), opaque cursor Load more, in-memory message selection, lifecycle/error recovery UX. No AI analysis, raw body/detail, or workflow/send. Live mailbox provider calls were not performed.
- **15D is Completed:** explicit selected-message analyze in the mailbox workspace, `communications:analyze` permission-aware UX, in-memory analysis display (summary, priority, category, action items, read-only AI draft suggestion), re-analyze, and safe error/retry handling. No WorkflowAction, send, raw body/detail, or analysis history page. Live Foundry/Bedrock inference was not performed.
- **15E is Completed:** explicit WorkflowAction proposal from the current `analysis_id`, immutable snapshot review, explicit Approve/Reject, explicit Send with a mandatory confirmation dialog, EXECUTING uncertainty without retry, and terminal EXECUTED/FAILED UX. Live send was not performed. Backend workflow/execute application code was not changed.
- **15F is Completed:** context-safe error mapping, 401 Sign in recovery without redirect loops, application ErrorBoundary, confirmation-dialog focus trap/return, semantic landmarks, keyboard and focus-visible hardening, non-color status text, responsive/narrow layouts, and axe-backed component tests. Explicit send/execute safety from 15E is unchanged. Live browser validation remains 15G.
- Later slices remain deferred: live browser validation and final documentation/phase closure.

Phase 14 remains **Completed**.

## 15A — Frontend Foundation + Browser Authentication

Same-repository SPA under `frontend/`.

```text
Unauthenticated shell
→ MSAL loginRedirect
→ sessionStorage MSAL cache
→ acquireTokenSilent
→ Authorization: Bearer <token>
→ GET /api/v1/analyses?limit=1
```

`/api/v1/health` is public and is not the authenticated smoke contract.

Local CORS:

```text
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Empty CORS configuration keeps the API backend-only. Wildcard origins are rejected. CORS credentials are never enabled.

### Local frontend setup

1. Copy `frontend/.env.example` to `frontend/.env`.
2. Set public SPA values (`VITE_ENTRA_TENANT_ID`, `VITE_ENTRA_SPA_CLIENT_ID`, `VITE_ECI_API_SCOPES`).
3. From `frontend/`: `npm install`, `npm run dev`.
4. From the repository root, run FastAPI as usual with `CORS_ALLOWED_ORIGINS=http://localhost:5173`.
5. Optional mailbox-OAuth return: set `FRONTEND_OAUTH_RETURN_URL=http://localhost:5173` on the API. When unset, callbacks keep the existing sanitized JSON responses.

`VITE_ECI_API_SCOPES` must be the full delegated identifiers using exact permission names:

```text
communications:read
communications:analyze
communications:connect
communications:workflow
communications:send
```

Example shape only:

```text
api://<eci-api-client-id>/communications:read
```

Do not use `communications.read` or `.default` as the browser permission strategy.

Live browser authentication requires a dedicated Entra SPA/public-client registration. That operator step is deferred. Automated tests mock MSAL and tokens.

### Out of scope for 15A

- Connector dashboard and mailbox listing UI
- Gmail or Microsoft Graph connect UI
- OAuth callback → frontend redirect
- Analysis, workflow, approve/reject, or send UI
- Creating or mutating Entra/Azure/AWS resources
- Database migration

## 15B — Connector Dashboard + OAuth UX

Authenticated SPA dashboard for owned Gmail and Microsoft Graph connector lifecycle.

```text
ECI browser principal
→ MSAL ECI bearer token
→ GET /api/v1/connector-accounts (communications:read)
→ Connect / Reconnect / Disconnect (communications:connect)
→ FastAPI mailbox OAuth start
→ provider consent
→ FastAPI callback
→ optional 302 to FRONTEND_OAUTH_RETURN_URL
→ SPA refreshes owned accounts
```

`GET /api/v1/connector-accounts` returns a bounded owned collection. The public item includes `id`, `provider`, `status`, `granted_capabilities`, `created_at`, and `updated_at`. It omits `credential_ref`, `external_account_id`, locators, and tokens.

Mailbox OAuth stays server-side. The SPA calls existing authorize/reauthorize endpoints, then navigates to the returned `authorization_url`. PKCE, state, token exchange, and credential persistence do not run in the browser. MSAL remains ECI login only.

`FRONTEND_OAUTH_RETURN_URL` is optional, server-configured, and never taken from callback query input. Success returns `?oauth=success&provider=gmail|microsoft_graph`. Failures return only `denied`, `expired`, `identity_mismatch`, or `failed`. Authorization codes, state, tokens, locators, and raw provider errors are not placed on the Location header. When the setting is unset, callbacks keep the previous sanitized JSON behavior.

Disconnect requires an explicit confirmation dialog. Frontend `scp` checks are UX only; FastAPI remains authoritative.

### Out of scope for 15B

- Mailbox message listing, pagination, selection, or analysis UI
- Workflow, approve/reject, or send UI
- Live provider OAuth or Entra SPA provisioning
- Database migration

## 15C — Mailbox Workspace + Pagination

Authenticated SPA mailbox workspace on the existing Phase 14 list contract.

```text
ECI browser principal
→ Connector Dashboard
→ Open mailbox (ACTIVE only)
→ GET /api/v1/connector-accounts/{id}/messages?page_size=10
→ provider-neutral metadata list
→ select one message (memory only)
→ Load more with opaque next_cursor
```

Routes:

- `/` — connector dashboard
- `/mailbox/:connectorAccountId` — mailbox workspace

React Router was added for this slice because the workspace is a distinct product surface with back-navigation. There is no analysis, workflow, or settings route tree.

The SPA consumes `GET /api/v1/connector-accounts/{connector_account_id}/messages` unchanged. Authorization remains `communications:read`. The UI page size is `10`, matching the frozen backend default. `next_cursor` is stored only in TanStack Query page state, passed back unchanged, never decoded, never rendered, and never placed in the URL.

Selection is React state only. The selected-message panel shows sender, subject, timestamps, and provider label. It does not call analyze, fetch raw message detail, or show `provider_message_id`.

Mailbox queries use `useInfiniteQuery` with `pageParam` as the opaque cursor. Pagination is user-triggered Load more. There is no prefetch, polling, or automatic extra page fetch. Retry is disabled (`retry: false`); 503 recovery is a manual Try again. Invalid cursor (400) offers Refresh mailbox, which discards the cursor chain and requests a fresh first page. 409 invalidates the connector-account query and returns the user toward reconnect UX without retrying mailbox read.

Frontend `scp` checks remain UX only. FastAPI remains authoritative.

### Out of scope for 15C

- Selected-message AI analysis or analysis history
- Raw message body/detail, search, attachments, or snippet/preview expansion
- Workflow, approve/reject, send, or execute
- Mailbox synchronization, workers, webhooks, or notifications
- Live provider OAuth or Entra SPA provisioning
- Database migration

## 15D — Analysis Experience

Explicit selected-message AI analysis inside the existing mailbox workspace.

```text
ECI browser principal
→ ACTIVE mailbox workspace
→ select one message (no analyze)
→ Analyze message (communications:read + communications:analyze)
→ POST /api/v1/connector-accounts/{id}/messages/analyze
→ display summary, priority, category, action items, read-only AI draft suggestion
```

Analyze is user-triggered. Opening a mailbox, selecting a row, loading more, or refreshing the list does not analyze. The SPA consumes the existing Phase 14 analyze contract unchanged: JSON body `{ "provider_message_id": "<opaque>" }`. The response reuses `CommunicationAnalysisResponse`. Direct-text `POST /api/v1/communications/analyze` is not used.

Analysis uses TanStack `useMutation` with `retry: false`. One Analyze activation produces one POST. Re-analyze is a second explicit request. While re-analysis is pending, the previous successful result remains visible. A failed re-analysis keeps that previous result and shows a non-destructive error.

Displayed analysis is browser-memory state for the current selection. Changing the selected message clears it. Manual mailbox refresh also clears it, even when the same message remains, so a prior result is not shown as current. Results are not written to localStorage, IndexedDB, or the URL. `provider_message_id` and `analysis_id` stay internal. `analysis_id` is retained in memory for Phase 15E. Raw message bodies are not requested or rendered.

The AI draft is labelled **AI draft suggestion** and **Not approved or sent**. It is read-only. Phase 15D does not create a `WorkflowAction`, approve, reject, execute, or send.

Frontend `scp` checks remain UX only. A signed-in user with `communications:read` but without `communications:analyze` can still browse and select messages; Analyze is disabled with an explanation. FastAPI remains authoritative. Analyze 409 invalidates the connector-account query and moves the workspace toward reconnect UX without retrying analyze. Transient 503 allows a manual Retry and does not invent `REAUTH_REQUIRED`.

### Out of scope for 15D

- WorkflowAction proposal, approval, rejection, execute, or send
- Editable draft intended for send
- Raw message body/detail, analysis history page, or delete-analysis UI
- Mailbox-wide, bulk, automatic, or background analysis
- Live Foundry/Bedrock inference or Entra SPA provisioning
- Database migration

## 15E — Workflow Review + Explicit Send UX

Explicit proposal, review, approval, and confirmed send on top of the existing Phase 12 workflow contract and the Phase 15D analysis result.

```text
ECI browser principal
→ ACTIVE mailbox workspace
→ explicit Analyze (communications:analyze)
→ analysis_id + read-only AI draft suggestion
→ explicit Propose reply (communications:workflow)
→ PENDING immutable snapshot
→ explicit Approve or Reject
→ if APPROVED: explicit Send approved reply (communications:send)
→ confirmation dialog
→ POST /api/v1/workflow-actions/{action_id}/execute
```

The UI keeps these states distinct:

```text
AI draft suggestion
≠ WorkflowAction proposal
≠ approved communication
≠ executed/sent communication
```

Proposal uses the in-memory `analysis_id` from Phase 15D. The create body is only `{ "analysis_id": "<uuid>" }`. The SPA does not supply reply text, recipients, or status. If `analysis_id` is missing, proposal is unavailable; the SPA does not invent an id, reconstruct an action, or re-analyze automatically.

Workflow mutations use TanStack `useMutation` with `retry: false`. One Propose, Approve, Reject, or confirmed Send produces one matching request. Analysis success, mount, selection, re-analysis, and route changes do not create, approve, or execute a `WorkflowAction`. Approve does not call execute. Opening or canceling the send confirmation does not execute.

Backend status is authoritative. The SPA uses the mutation response, or `GET /api/v1/workflow-actions/{action_id}` after execute 409/500/503 and for manual Refresh status. It does not fabricate PENDING→APPROVED or APPROVED→EXECUTED locally.

Send is shown only for `approved` plus `communications:send`. PENDING has Approve/Reject only. REJECTED, EXECUTING, EXECUTED, and FAILED do not expose Send. EXECUTING after HTTP 503 is uncertainty, not failure: the UI tells the user not to send again and does not offer Retry send. FAILED is terminal. EXECUTED means backend execution completed according to existing executor semantics, not recipient delivery.

Frontend `scp` checks remain UX only. FastAPI remains authoritative. Changing the selected message, mailbox refresh, or a successful re-analysis clears the current in-memory workflow view without deleting the backend action. Live Gmail/Graph send was not performed.

No new ADR is required. ADR-015, ADR-017, ADR-019, ADR-020, and ADR-025 already cover the workflow/send boundary and the browser client.

### Out of scope for 15E

- Automatic proposal, approval, or send
- Live provider send, execute retry, outbox, reconciliation, workers, or webhooks
- Editable workflow/approved snapshots, workflow history, or analysis-history retrieval
- Broad accessibility/responsive hardening (15F) or final docs/live validation (15G)
- Entra SPA provisioning or database migration

## 15F — Error / Accessibility / Responsive Hardening

Hardened the Phase 15A–15E SPA without adding product features or changing backend contracts.

```text
raw HTTP status / EciApiError
→ operation-specific presentProductError
→ ProductErrorState (stable copy + Sign in / Try again / Refresh / Back to dashboard)
```

401 is session-unusable, with an explicit Sign in action and no automatic redirect loop. 403 remains permission-specific. Mailbox 400 still discards the cursor chain. Mailbox/analyze 409 still refreshes connector lifecycle. Transient 503 never invents `REAUTH_REQUIRED`. Execute 503 remains uncertain and never offers Try again or Retry send.

Accessibility baseline:

- `header` / `main` landmarks, mailbox `nav`, and heading order under the selected-message panel
- keyboard operation for connectors, message rows, Analyze/Propose/Approve/Reject/Send, and dialogs
- `:focus-visible` on buttons and links
- confirmation dialogs: `role="dialog"`, labelled title/description, focus entry, Tab trap, Escape/Cancel, focus return
- `role="status"` / `role="alert"` for loading, errors, and EXECUTING uncertainty
- readable (not color-only) connector, priority, and workflow status text
- nearby permission explanations for disabled Analyze/Propose/Send

Responsive web (not a native app or PWA): stacked dashboard/mailbox/workflow actions at narrow widths, `min-w-0` / `break-words` for long subjects, senders, and AI/workflow text, and `min-h-11` touch targets. An application ErrorBoundary shows a generic safe fallback with Reload and Back to dashboard. No new ADR. ADR-025 remains the browser architecture.

`eslint-plugin-jsx-a11y` was not added: it does not declare ESLint 10 peer support, and forcing it would break peer-autoinstall of `@testing-library/dom`. Automated coverage uses `jest-axe` plus focused RTL tests.

### Out of scope for 15F

- Live Entra SPA sign-in, live Gmail/Graph OAuth, live mailbox list, live analysis, or live send
- New backend endpoints, schema, or Phase 12–14 semantic changes
- Native mobile, PWA, bundle-splitting, or repository-wide README reconciliation (15G)

## Planned later slices

Phase 15G performs live browser validation, documentation closure, and Phase 15 completion. Later slices must not collapse ECI login, Gmail mailbox OAuth, and Microsoft mailbox OAuth into one browser flow.

## Cloud implications

No new Azure or AWS resources are created by 15A. The existing ECI API resource remains the token audience. A dedicated SPA registration is an operator step for live browser use.
