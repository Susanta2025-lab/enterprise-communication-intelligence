# ADR-009: Application-User Authentication and Authorization

## Status

Accepted

The decision is implemented. Phase 8A JWT validation is in the codebase. Phase 8D configured a live single-tenant Microsoft Entra ID API resource. Azure real-bearer authorized requests are verified. AWS missing-token and JWKS fail-closed paths are verified. AWS real-bearer authorized inference is deferred until TLS exists.

## Date

Phase 8 (Production Hardening)

## Context

ECI needed application-user authentication without coupling the API to a specific identity-provider SDK, a user database, or cloud Easy Auth. Production must fail closed. The first live identity provider is Microsoft Entra ID, but the application validates a normal OIDC JWT.

Three identity classes must stay separate:

- API callers (application-user JWT)
- runtime workload identity to Foundry / Bedrock
- GitHub deployment identity

Live issuer, audience, and JWKS values are configuration. Documentation uses placeholders only — no real tenant IDs or client IDs.

## Decision

Validate incoming bearer tokens with provider-independent OIDC JWT checks (`iss`, `aud`, `exp`, RS256 JWKS) and require permission `communications:analyze` from bounded claims `scp`, `scope`, or `roles`.

```text
Client
→ Microsoft Entra ID (or any OIDC IdP)
→ access token
→ ECI TokenValidator
→ communications:analyze
→ POST /api/v1/communications/analyze
```

Live Entra configuration is a single-tenant resource application (`eci-api-auth-dev`) with `requestedAccessTokenVersion=2`, Application ID URI `api://<ECI_API_CLIENT_ID>`, and one delegated scope `communications:analyze`. Runtime settings are identifiers and metadata, not secrets:

```env
AUTH_MODE=oidc
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_AUDIENCE=<ECI_API_CLIENT_ID>
OIDC_JWKS_URL=https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
OIDC_REQUIRED_PERMISSION=communications:analyze
```

`APP_ENV=production` requires `AUTH_MODE=oidc`. Health and readiness remain public. Production OpenAPI routes stay disabled.

A DEV-ONLY public client (`eci-auth-verifier-dev`) exists for interactive verification. It has no client secret.

## Alternatives Considered

- **Microsoft Entra Easy Auth / container platform auth** — rejected. It would couple the API to Azure and would not apply the same way on AWS.
- **Cognito or a user database** — rejected. Persistence and a second IdP SDK are out of scope for Phase 8.
- **API keys** — rejected. They are long-lived secrets and do not express delegated user permission.

## Consequences

- ECI remains IdP-agnostic in application code. Entra is the first registered issuer, not an SDK dependency.
- Entra v2 access tokens use the API application ID as audience.
- A public verification client exists; operators must not add a client secret to that app or to ECI Settings.
- Azure authorized inference was verified over HTTPS with a real bearer token.
- AWS real-bearer authorized inference is deferred until TLS exists. Never send a real bearer token over the AWS HTTP verification path.

## Benefits

- fail-closed production startup
- permission-based authorization without a user store
- one auth design for Azure and AWS runtimes
- no long-lived API keys for application users

## Trade-offs

- operators must provision issuer, audience, and JWKS before deploying a production image
- AWS cannot receive a real bearer token over the current HTTP verification path
- token issuance stays in the identity provider; ECI does not issue tokens

## Deferred Work

- AWS real-bearer authorized inference after domain/ACM TLS
- additional identity providers behind the same OIDC validator
- a user database, session store, or refresh-token handling in ECI

## Related Components

- `app/core/security.py`
- `app/core/config.py`
- `app/api/dependencies.py`
- [Authentication](../cloud/authentication.md)
- [API Overview](../api/overview.md)
- ADR-005 (Synchronous REST API)
- ADR-010 (Multi-Cloud Production Ingress)
- ADR-011 (Secretless GitHub Actions Multi-Cloud CI/CD)
