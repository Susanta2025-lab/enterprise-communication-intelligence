# ECI Platform API Documentation

This directory documents the REST API implemented through Phase 9 of the ECI Platform roadmap.

## Contents

- [Overview](overview.md) — purpose, base URL, versioning, authentication, and request flow
- [Endpoints](endpoints.md) — all implemented routes and their behavior
- [Request/Response Models](request-response-models.md) — field-level schema reference
- [Error Handling](error-handling.md) — validation, exception translation, and status codes
- [Examples](examples.md) — `curl` examples against a local server

## Current Provider Status

The API currently defaults to `AI_PROVIDER=mock` (see `.env.example`). `MicrosoftFoundryProvider` is available when `AI_PROVIDER=microsoft_foundry` and Foundry settings are present. `AmazonBedrockProvider` is available when `AI_PROVIDER=amazon_bedrock` and Bedrock settings are present; live ECI → Bedrock verification is complete. See [Provider Abstraction](../architecture/provider-abstraction.md), [Microsoft Foundry](../cloud/azure-ai-foundry.md), and [Amazon Bedrock](../cloud/amazon-bedrock.md).

## Scope

This documentation reflects the REST API plus Phase 6 cloud AI providers, Phase 8 application-user OIDC, and Phase 9 user-owned analysis history. Responses include `X-Request-ID` for operational correlation. Persistence details stay behind the API: callers see optional `analysis_id` and history resources, not SQLAlchemy or PostgreSQL types. Cloud hosting is documented in [`docs/cloud/deployment.md`](../cloud/deployment.md). Persistence strategy is documented in [`docs/cloud/persistence.md`](../cloud/persistence.md). See [`docs/roadmap/README.md`](../roadmap/README.md) for phase status.
