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

Phase 15 is **In progress**. **15A, 15B, 15C, and 15D are Completed.** Phase 15E is next.

- **15A is Completed:** frontend foundation, MSAL browser authentication, typed API client, protected analyses smoke contract, explicit CORS allowlist, ADR-025. Live Entra SPA registration and real browser sign-in were not performed.
- **15B is Completed:** owned connector-account dashboard, Gmail/Microsoft Graph connect and exact-account reauthorize UX, disconnect confirmation, optional `FRONTEND_OAUTH_RETURN_URL` callback return, sanitized OAuth return handling in the SPA. Mailbox OAuth remains server-side. Live provider OAuth and Entra SPA registration were not performed.
- **15C is Completed:** connected-mailbox workspace for ACTIVE Gmail and Microsoft Outlook connectors, bounded first-page load (`page_size=10`), opaque cursor Load more, in-memory message selection, lifecycle/error recovery UX. No AI analysis, raw body/detail, or workflow/send. Live mailbox provider calls were not performed.
- **15D is Completed:** explicit selected-message analyze in the mailbox workspace, `communications:analyze` permission-aware UX, in-memory analysis display (summary, priority, category, action items, read-only AI draft suggestion), re-analyze, and safe error/retry handling. No WorkflowAction, send, raw body/detail, or analysis history page. Live Foundry/Bedrock inference was not performed.
- Later slices remain deferred: workflow review and explicit send UX, and final documentation/live validation.

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

## Planned later slices

Phase 15E adds workflow review and explicit send UX on this analysis result. Later slices must not collapse ECI login, Gmail mailbox OAuth, and Microsoft mailbox OAuth into one browser flow.

## Cloud implications

No new Azure or AWS resources are created by 15A. The existing ECI API resource remains the token audience. A dedicated SPA registration is an operator step for live browser use.
