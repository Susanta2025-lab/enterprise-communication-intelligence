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

Phase 15 is **In progress**. **15A is Completed.** Phase 15B is next.

- **15A is Completed:** frontend foundation, MSAL browser authentication, typed API client, protected analyses smoke contract, explicit CORS allowlist, ADR-025. Live Entra SPA registration and real browser sign-in were not performed.
- **15B — Connector Dashboard + OAuth UX:** not started.
- Later slices remain deferred: OAuth callback frontend return, mailbox listing UI, analysis/workflow/send UI, and final documentation/live validation.

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

## Planned later slices

Later Phase 15 slices add product UX on this foundation. They must not collapse ECI login, Gmail mailbox OAuth, and Microsoft mailbox OAuth into one browser flow.

## Cloud implications

No new Azure or AWS resources are created by 15A. The existing ECI API resource remains the token audience. A dedicated SPA registration is an operator step for live browser use.
