# Phase 06 Cloud Deployment

## Objective

Introduce production-capable cloud AI integration while preserving the provider-independent architecture established in Phases 1–5.

## Business Value

- Enables real model inference for communication analysis without changing the domain, application, or REST contracts.
- Keeps local/offline development available through `MockAIProvider`.
- Uses Microsoft Entra ID so local Azure CLI login and future Managed Identity share the same application code.

## Current sub-phase: 6A Microsoft Foundry provider

Phase 6 is in progress. **6A is implemented:** `MicrosoftFoundryProvider` behind the existing `AIProvider` interface.

Not part of 6A (still later Phase 6 work unless separately requested):

- Amazon Bedrock provider
- Docker / cloud hosting
- Azure Key Vault or AWS Secrets Manager
- Azure Monitor or CloudWatch

## Deliverables (6A)

- `app/providers/microsoft_foundry/` — `MicrosoftFoundryProvider`
- Settings for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT`
- Factory selection via `AI_PROVIDER=microsoft_foundry`
- Offline unit tests with mocked Foundry SDK clients
- Cloud and architecture documentation for the implemented adapter
- ADR-006 Microsoft Foundry Provider

## Tasks

- [x] Implement `MicrosoftFoundryProvider` against the existing `AIProvider` contract
- [x] Authenticate with `DefaultAzureCredential` (no API key)
- [x] Call Microsoft Foundry through `AIProjectClient` → `get_openai_client()` → `responses.create(...)`
- [x] Keep mock provider working without Foundry configuration
- [x] Add deterministic offline tests
- [x] Document verified Foundry development infrastructure without secrets
- [ ] Amazon Bedrock provider
- [ ] Container and cloud hosting

## Architectural Decisions

- Cloud SDKs stay inside the provider adapter.
- Structured JSON Schema output is requested from the Responses API, then validated into existing domain models.
- Foundry settings are required only when `AI_PROVIDER=microsoft_foundry`.

See [ADR-006](../decisions/ADR-006-azure-ai-foundry.md).

## Acceptance Criteria

- [x] `MockAIProvider` still works
- [x] `MicrosoftFoundryProvider` implements `AIProvider`
- [x] Factory selects Microsoft Foundry via configuration
- [x] No API key is required
- [x] Domain/application/API layers remain provider-independent
- [x] Automated tests make no real Azure network calls
- [ ] Full Phase 6 cloud deployment (hosting, Bedrock, secrets, monitoring) — not in 6A

## Risks and Trade-offs

- Foundry inference has network, RBAC, quota, and token-cost dependencies.
- Automated tests cannot prove live model quality; a manual paid inference check remains an operator step.

## Lessons Learned

To be captured when Phase 6 hosting work is completed.

## Next Phase

Phase 7 – Observability remains not started until Phase 6 is completed.
