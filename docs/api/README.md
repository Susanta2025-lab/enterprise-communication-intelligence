# ECI Platform API Documentation

This directory documents the REST API implemented through completed Phase 13 of the ECI Platform roadmap. Phase 10 added no connector message-ingestion HTTP endpoints. Phase 11C adds workflow proposal and approval routes. Phase 12E adds `POST /api/v1/workflow-actions/{action_id}/execute` protected by `communications:send`. Phase 13C/13D add Gmail and Microsoft mailbox authorize (`communications:connect`) and unauthenticated provider callbacks. Phase 13F adds owned disconnect and reauthorize. There is no retry route and no connector fetch/analyze HTTP.

## Contents

- [Overview](overview.md) — purpose, base URL, versioning, authentication, and request flow
- [Endpoints](endpoints.md) — all implemented routes and their behavior
- [Request/Response Models](request-response-models.md) — field-level schema reference
- [Error Handling](error-handling.md) — validation, exception translation, and status codes
- [Examples](examples.md) — `curl` examples against a local server

## Current Provider Status

The API currently defaults to `AI_PROVIDER=mock` (see `.env.example`). `MicrosoftFoundryProvider` is available when `AI_PROVIDER=microsoft_foundry` and Foundry settings are present. `AmazonBedrockProvider` is available when `AI_PROVIDER=amazon_bedrock` and Bedrock settings are present; live ECI → Bedrock verification is complete. See [Provider Abstraction](../architecture/provider-abstraction.md), [Microsoft Foundry](../cloud/azure-ai-foundry.md), and [Amazon Bedrock](../cloud/amazon-bedrock.md).

## Scope

This documentation reflects the REST API plus Phase 6 cloud AI providers, Phase 8 application-user OIDC, Phase 9 user-owned analysis history, Phase 11C workflow proposal/approval, Phase 12E user-approved execute, and Phase 13 mailbox OAuth lifecycle (Gmail/Microsoft authorize and callbacks, disconnect, reauthorize). Phase 12F documents 200 FAILED versus 503 EXECUTING. Phase 13F adds confirmed permanent refresh failure as 200 FAILED plus `REAUTH_REQUIRED`. Phase 10 connector adapters are not exposed as message-ingestion HTTP routes. Responses include `X-Request-ID` for operational correlation. Persistence details stay behind the API: callers see optional `analysis_id`, history resources, owned workflow actions, and sanitized connector-account metadata, not SQLAlchemy, PostgreSQL types, `credential_ref`, or tokens. Cloud hosting is documented in [`docs/cloud/deployment.md`](../cloud/deployment.md). Persistence strategy is documented in [`docs/cloud/persistence.md`](../cloud/persistence.md). See [`docs/roadmap/README.md`](../roadmap/README.md) for phase status.
