# ADR-025: Browser Frontend and Authentication Architecture

## Status

Accepted

Implemented in Phase 15A as the durable browser foundation. Live Entra SPA registration and real browser sign-in were validated in Phase 15G on the local Vite SPA against local FastAPI.

## Date

Phase 15 (Browser Frontend)

## Context

ECI is a bearer-token FastAPI API. Through Phase 14, callers obtained ECI access tokens outside the repository (scripts, a DEV-ONLY public verifier, or equivalent). Product use now requires a browser application.

Three authentication/delegation concepts must stay separate:

- ECI application login (Entra OIDC → ECI bearer token → FastAPI authorization)
- Gmail delegated mailbox authorization (Google OAuth, server-side)
- Microsoft Graph delegated mailbox authorization (Microsoft OAuth, server-side)

The browser must not receive mailbox OAuth client secrets, must not become a BFF, and must not be treated as the authorization authority. FastAPI remains authoritative for authentication and authorization.

## Decision

Keep the frontend in this repository under `frontend/` as a React + TypeScript + Vite SPA.

Authenticate the browser with MSAL as a public client. The SPA obtains delegated ECI access tokens and calls FastAPI with `Authorization: Bearer <token>`. There is no backend-for-frontend, no application session cookie, and no frontend client secret.

Mailbox OAuth remains server-side. The SPA does not implement Google or Microsoft mailbox consent, does not store mailbox tokens, and does not receive mailbox OAuth credentials.

Use TanStack Query for server state. Keep a thin authentication context around MSAL. Do not introduce Redux.

Allow the local Vite origin to call the API only through an explicit CORS origin allowlist (`CORS_ALLOWED_ORIGINS`). Never use `*`. Never enable CORS credentials.

Prefer a dedicated Entra SPA/public-client registration for live browser operation. The existing ECI resource API remains the token audience. The SPA client ID is configuration supplied by the operator. Phase 15A does not create or mutate Entra app registrations.

Browser MSAL cache uses sessionStorage. The SPA does not persist mailbox or product content in durable browser storage.

Frontend permission helpers may inspect `scp` only for UX. Backend token validation remains authoritative.

## Alternatives Considered

- **Backend-for-frontend with application cookies** — rejected. It would add a session layer, change the established bearer-token API, and mix browser login with API authorization.
- **Confidential-client SPA or frontend client secret** — rejected. A browser cannot keep a client secret.
- **Separate frontend repository** — rejected. Same-repository `frontend/` keeps the product contract and local CORS origin in one place while leaving Python and Node toolchains separated.
- **Moving mailbox OAuth into the SPA** — rejected. Gmail and Graph delegated authorization stay on the existing server-side lifecycle.

## Consequences

- Local development can run Vite on `http://localhost:5173` against FastAPI on `http://localhost:8000` when CORS origins are configured.
- Mailbox connect/reconnect UX calls existing server-side authorize endpoints, then returns the browser to a fixed configured frontend URL (`FRONTEND_OAUTH_RETURN_URL`) after FastAPI completes token exchange. Mailbox OAuth credentials and tokens never cross to the SPA. When the return URL is unset, callbacks keep sanitized JSON responses.
- Live browser sign-in requires an operator-provisioned SPA client ID, redirect URI, and explicit `communications:*` delegated scopes. Phase 15G validated this on the local Vite SPA with a dedicated Entra SPA registration; cloud-hosted browser deployment was not part of that proof.

## Benefits

- FastAPI remains a bearer-token API
- browser identity stays separate from mailbox delegation
- no SPA client secret
- explicit CORS allowlist
- frontend and backend toolchains stay isolated

## Trade-offs

- operators must provision a dedicated SPA registration before live browser authentication
- MSAL redirect/session behavior is browser-specific and is not a server session
- CORS must be configured for each allowed frontend origin

## Related Components

- `frontend/`
- `app/core/config.py`
- `app/main.py`
- [ADR-009](ADR-009-application-user-authentication.md)
- [ADR-021](ADR-021-mailbox-delegated-oauth-authorization-architecture.md)
- [Phase 15](../roadmap/phase-15-frontend.md)
