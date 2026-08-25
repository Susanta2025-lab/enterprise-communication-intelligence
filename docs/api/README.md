# ECI Platform API Documentation

This directory documents the REST API implemented through completed Phase 14 of the ECI Platform roadmap. Phase 10 added no connector message-ingestion HTTP endpoints. Phase 11C adds workflow proposal and approval routes. Phase 12E adds `POST /api/v1/workflow-actions/{action_id}/execute` protected by `communications:send`. Phase 13C/13D add Gmail and Microsoft mailbox authorize (`communications:connect`) and unauthenticated provider callbacks. Phase 13F adds owned disconnect and reauthorize. Phase 14 adds `communications:read`, bounded mailbox listing, and selected-message mailbox-backed analyze. Direct-text analyze remains distinct. There is no retry route. There is no mailbox sync, search, attachment, bulk, webhook, or worker route.

## Contents

- [Overview](overview.md) — purpose, base URL, versioning, authentication, and request flow
- [Endpoints](endpoints.md) — all implemented routes and their behavior
- [Request/Response Models](request-response-models.md) — field-level schema reference
- [Error Handling](error-handling.md) — validation, exception translation, and status codes
- [Examples](examples.md) — `curl` examples against a local server

## Current Provider Status

The API currently defaults to `AI_PROVIDER=mock` (see `.env.example`). `MicrosoftFoundryProvider` is available when `AI_PROVIDER=microsoft_foundry` and Foundry settings are present. `AmazonBedrockProvider` is available when `AI_PROVIDER=amazon_bedrock` and Bedrock settings are present; live ECI → Bedrock verification is complete. See [Provider Abstraction](../architecture/provider-abstraction.md), [Microsoft Foundry](../cloud/azure-ai-foundry.md), and [Amazon Bedrock](../cloud/amazon-bedrock.md).

## Scope

This documentation reflects the REST API plus Phase 6 cloud AI providers, Phase 8 application-user OIDC, Phase 9 user-owned analysis history, Phase 11C workflow proposal/approval, Phase 12E user-approved execute, Phase 13 mailbox OAuth lifecycle (Gmail/Microsoft authorize and callbacks, disconnect, reauthorize), and Phase 14 connected-mailbox listing and selected-message analyze. Phase 12F documents 200 FAILED versus 503 EXECUTING. Phase 13F adds confirmed permanent refresh failure as 200 FAILED plus `REAUTH_REQUIRED`. Phase 14 listing requires `communications:read`. Mailbox-backed analyze requires `communications:read` and `communications:analyze`. Direct-text analyze remains `communications:analyze` only. Responses include `X-Request-ID` for operational correlation. Persistence details stay behind the API: callers see optional `analysis_id`, history resources, owned workflow actions, and sanitized connector-account metadata, not SQLAlchemy, PostgreSQL types, `credential_ref`, or tokens. Cloud hosting is documented in [`docs/cloud/deployment.md`](../cloud/deployment.md). Persistence strategy is documented in [`docs/cloud/persistence.md`](../cloud/persistence.md). Phase 14 live proof used local runtime + real Entra OIDC + real Gmail/Graph mailboxes + local PostgreSQL + `MockAIProvider`; it did not certify retained ACA/ECS deployments or Foundry/Bedrock inference. See [`docs/roadmap/README.md`](../roadmap/README.md) for phase status.
