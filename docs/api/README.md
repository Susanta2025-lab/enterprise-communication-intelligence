# ECI Platform API Documentation

This directory documents the REST API implemented through Phase 5 of the ECI Platform roadmap.

## Contents

- [Overview](overview.md) — purpose, base URL, versioning, and request flow
- [Endpoints](endpoints.md) — all implemented routes and their behavior
- [Request/Response Models](request-response-models.md) — field-level schema reference
- [Error Handling](error-handling.md) — validation, exception translation, and status codes
- [Examples](examples.md) — `curl` examples against a local server

## Current Provider Status

The API currently runs with `AI_PROVIDER=mock` by default (see `.env.example`). All communication analysis is produced by the deterministic `MockAIProvider`; no Azure or AWS provider is implemented or configured. See [Provider Abstraction](../architecture/provider-abstraction.md) for details.

## Scope

This documentation reflects only what is implemented through **Phase 5 – REST API**. Cloud provider integrations, authentication, persistence, and deployment are future work and are not described here as if they exist. See [`docs/roadmap/README.md`](../roadmap/README.md) for phase status.
