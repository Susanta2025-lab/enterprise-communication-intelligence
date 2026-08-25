# ECI frontend

React + TypeScript + Vite SPA for ECI application login, connector dashboard, mailbox browsing, and selected-message analysis.

Mailbox OAuth stays on the FastAPI server. The SPA obtains only ECI bearer access tokens through MSAL.

## Local setup

1. Copy `.env.example` to `.env`.
2. Fill in the public Entra SPA values. There is no client secret.
3. `VITE_ECI_API_SCOPES` must list the full delegated identifiers with exact `communications:*` names.
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

Selected-message analysis is explicit. Opening a mailbox, selecting a row, loading more, or refreshing does not analyze. Analyze requires `communications:read` and `communications:analyze`. Results stay in browser memory. The AI draft is a read-only suggestion and is not approved or sent. Raw message bodies are not displayed.

Live browser sign-in requires an operator-provisioned Entra SPA/public-client registration. That step is not performed by the application.

## Scripts

```bash
npm run dev
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```
