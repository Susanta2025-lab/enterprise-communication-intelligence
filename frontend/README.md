# ECI frontend

React + TypeScript + Vite SPA for ECI application login (Microsoft Entra External ID / MSAL), connector dashboard, mailbox browsing, selected-message analysis, secure attachment metadata / explicit Analyze, and explicit workflow review/send.

Mailbox OAuth stays on the FastAPI server. The SPA obtains only ECI bearer access tokens through MSAL. Application login is distinct from Gmail and Outlook mailbox OAuth.

## Local setup

1. Copy `.env.example` to `.env`.
2. Fill in the public External ID / MSAL SPA values (`VITE_ENTRA_AUTHORITY`, client id, redirect URI, API scopes). There is no client secret.
3. `VITE_ECI_API_SCOPES` must list exactly the five ECI delegated scopes with exact `communications:*` names and a common `api://` resource.
4. Run the API with `CORS_ALLOWED_ORIGINS=http://localhost:5173`.
5. From this directory:

```bash
npm install
npm run dev
```

The SPA listens on `http://localhost:5173` by default.

Signed-in routes:

- `/` — connected-mailbox dashboard
- `/mailbox/:connectorAccountId` — mailbox workspace for one owned connector

Selected-message analysis is explicit. Opening a mailbox, selecting a row, loading more, or refreshing does not analyze. Analyze requires `communications:read` and `communications:analyze`. Results stay in browser memory. The AI draft is a read-only suggestion and is not approved or sent.

**Attachments (Phase 18):** the workspace lists attachment metadata for the selected message without downloading content. Explicit **Analyze attachment** retrieves and analyzes one attachment only after user action. Supported analysis formats today: PDF, DOCX, TXT. XLSX is unsupported (fail-closed). JPEG/PNG are gated when the AI adapter reports image input unavailable—do not present image analysis as live-supported. Attachment analysis cannot Propose, Approve, Execute, or Send.

Workflow review is also explicit. Propose reply requires `communications:workflow` and the current message-analysis `analysis_id`. The server snapshots the draft; the SPA does not edit the proposal. Approve and Reject are separate from Send. Send requires `communications:send`, an `approved` action, and a confirmation dialog. There is no automatic proposal, approval, or send. An uncertain `executing` outcome must not be retried.

Product errors are mapped by operation (connector, mailbox, analyze, attachment, workflow, execute), not by a single global HTTP-status string. A 401 offers Sign in and does not retry the failed request. `Try again` is used only where repeating the operation is safe. Execute uncertainty never offers Retry send.

The layout is a responsive web app. Narrow viewports stack dashboard and mailbox actions and drill into a selected message; desktop keeps the list beside the selected/analysis/workflow panel. Long subjects, senders, and AI/workflow text wrap. Confirmation dialogs trap focus and restore it on close.

Raw message bodies and raw attachment bytes are not displayed as durable browser storage. Mailbox, analysis, attachment, and workflow content stay in memory. The URL may include the opaque connector account id and, briefly, sanitized OAuth return parameters. Auth diagnostics are sanitized (no tokens, codes, state, nonce, or account identifiers).

Live browser sign-in, connector OAuth, mailbox list, selected-message analyze, and workflow review were validated in Phase 15G on the local Vite SPA against local FastAPI and PostgreSQL (historically with workforce Entra MSAL). Phase 17 cut product login to External ID. Phase 18 added attachment UX and live-validated attachment Analyze on Azure (Outlook→Foundry) and AWS (External ID + Gmail→Bedrock) without Send. Live Send/execute was not performed in Phase 15G or Phase 18.

## Scripts

```bash
npm run dev
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```
