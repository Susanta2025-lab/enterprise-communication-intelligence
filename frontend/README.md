# ECI frontend

React + TypeScript + Vite SPA for ECI application login.

This is the Phase 15A foundation. It does not include connector, mailbox, analysis, workflow, or send product UI.

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

Live browser sign-in requires an operator-provisioned Entra SPA/public-client registration. That step is not performed by the application.

## Scripts

```bash
npm run dev
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```
