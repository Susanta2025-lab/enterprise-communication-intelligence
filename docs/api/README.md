# ECI Platform API Documentation

This directory documents the REST API implemented through Phase 13D of the ECI Platform roadmap. Phase 10 added no connector HTTP endpoints. Phase 11C adds workflow proposal and approval routes. Phase 12E adds `POST /api/v1/workflow-actions/{action_id}/execute` protected by `communications:send`. Phase 13C adds Gmail mailbox authorize (`communications:connect`) and the unauthenticated Google callback. Phase 13D adds Microsoft Graph mailbox authorize and the unauthenticated Microsoft callback. There is no retry route.

## Contents

- [Overview](overview.md) — purpose, base URL, versioning, authentication, and request flow
- [Endpoints](endpoints.md) — all implemented routes and their behavior
- [Request/Response Models](request-response-models.md) — field-level schema reference
- [Error Handling](error-handling.md) — validation, exception translation, and status codes
- [Examples](examples.md) — `curl` examples against a local server

## Current Provider Status

The API currently defaults to `AI_PROVIDER=mock` (see `.env.example`). `MicrosoftFoundryProvider` is available when `AI_PROVIDER=microsoft_foundry` and Foundry settings are present. `AmazonBedrockProvider` is available when `AI_PROVIDER=amazon_bedrock` and Bedrock settings are present; live ECI → Bedrock verification is complete. See [Provider Abstraction](../architecture/provider-abstraction.md), [Microsoft Foundry](../cloud/azure-ai-foundry.md), and [Amazon Bedrock](../cloud/amazon-bedrock.md).

## Scope

This documentation reflects the REST API plus Phase 6 cloud AI providers, Phase 8 application-user OIDC, Phase 9 user-owned analysis history, Phase 11C workflow proposal/approval, Phase 12E user-approved execute, Phase 13C Gmail mailbox OAuth start/callback, and Phase 13D Microsoft Graph mailbox OAuth start/callback. Phase 12F documents 200 FAILED versus 503 EXECUTING. Phase 10 connector adapters are not exposed as HTTP routes. Responses include `X-Request-ID` for operational correlation. Persistence details stay behind the API: callers see optional `analysis_id`, history resources, and owned workflow actions, not SQLAlchemy or PostgreSQL types. Cloud hosting is documented in [`docs/cloud/deployment.md`](../cloud/deployment.md). Persistence strategy is documented in [`docs/cloud/persistence.md`](../cloud/persistence.md). See [`docs/roadmap/README.md`](../roadmap/README.md) for phase status.
