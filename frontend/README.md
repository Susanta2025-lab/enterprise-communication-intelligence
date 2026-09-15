# ECI frontend

React + TypeScript + Vite SPA for Enterprise Communication Intelligence (ECI).

**Register. Connect. Analyze.**

Supports application login (Microsoft Entra External ID / MSAL), connector dashboard, mailbox browsing, selected-message analysis, secure attachment metadata / explicit Analyze, explicit workflow review/send, and Platform Owner presentation (server-authoritative `/api/v1/me`).

## Identity boundary

**ECI application login ≠ mailbox login.**

- The SPA obtains only ECI bearer access tokens through MSAL (application identity).
- Mailbox OAuth (Gmail / Outlook) stays on the FastAPI server as a separate delegated authorization.
- Signing into ECI does **not** grant mailbox access.
- Mailbox OAuth does **not** determine Platform Owner authorization.

Owner status comes from `GET /api/v1/me` (`application_role` / `is_owner`). The Platform Owner badge and deployment indicator are UX-only; they do not authorize anything. Server-side `require_owner` (for example `GET /api/v1/admin/ping`) remains the security boundary.

Authenticated Platform Owners may see a deployment presentation indicator (Azure or AWS) with safe labels such as Cloud, AI provider, and Region. That metadata is presentation only—no authorization significance and no infrastructure secrets.

## Local setup

1. Copy `.env.example` to `.env`.
2. Fill in the public External ID / MSAL SPA values (`VITE_ENTRA_AUTHORITY`, client id, redirect URI, API scopes). There is no client secret.
3. `VITE_ECI_API_SCOPES` must list exactly the five ECI delegated scopes with exact `communications:*` names and a common `api://` resource.
4. Optionally set public deployment presentation vars (`VITE_ECI_CLOUD_PROVIDER`, `VITE_ECI_AI_PROVIDER`, `VITE_ECI_CLOUD_REGION`) as documented in `.env.example`.
5. Run the API with `CORS_ALLOWED_ORIGINS=http://localhost:5173`.
6. From this directory:

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

## Cloud-specific production builds

Use explicit Vite modes for manual cloud builds so Azure and AWS configuration do not leak across environments:

```bash
# Azure
npm run build:azure
# equivalent: npm run build -- --mode azure

# AWS
npm run build:aws
# equivalent: npm run build -- --mode aws
```

Do **not** treat a generic `npm run build` as the manual Azure (or AWS) deployment command.

Configuration notes:

- **Azure:** tracked `.env.azure` holds **public presentation metadata only** (`azure` / `microsoft_foundry` / `Spain Central`). Auth and API values stay in ignored `.env.azure.local` and/or CI/environment variables.
- **AWS:** tracked `.env.aws` holds **public presentation metadata only** (`aws` / `amazon_bedrock` / `eu-south-2`). Auth and API values stay in ignored `.env.aws.local` and/or CI/environment variables.
- Presentation vars are not credentials and not authorization inputs.

## Scripts

```bash
npm run dev
npm run typecheck
npm run lint
npm run test -- --run
npm run build
npm run build:azure
npm run build:aws
```

## Validation notes

Live browser sign-in, connector OAuth, mailbox list, selected-message analyze, and workflow review were validated in Phase 15G on the local Vite SPA against local FastAPI and PostgreSQL (historically with workforce Entra MSAL). Phase 17 cut product login to External ID. Phase 18 added attachment UX and live-validated attachment Analyze on Azure (Outlook→Foundry) and AWS (External ID + Gmail→Bedrock) without Send. Phase 19 added `/me`-backed Platform Owner awareness and the owner-only deployment indicator (presentation only).

Live Send/execute was not performed in Phase 15G or Phase 18. External business-user verification (Phase 17D) remains deferred and outside the currently completed release scope.

For external evaluation, use an ordinary application user—not the Platform Owner account. Application login alone does not authorize a mailbox.
