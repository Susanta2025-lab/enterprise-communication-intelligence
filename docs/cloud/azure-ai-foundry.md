# Microsoft Foundry

This document describes the implemented Microsoft Foundry provider. The former product name **Azure AI Foundry** appears only as legacy terminology.

## Role in the architecture

`MicrosoftFoundryProvider` implements the existing domain `AIProvider` contract. The application service, domain models, and REST API remain provider-independent.

```text
CommunicationAnalysisService
          │
          ▼
      AIProvider
       /   |   \
      /    |    \
   Mock  Foundry  AmazonBedrockProvider
           │
           ▼
   AIProjectClient
           │
           ▼
   Responses API
```

The adapter lives in `app/providers/microsoft_foundry/` so Azure SDK imports stay out of `app/domain`, `app/application`, and `app/api`.

## SDK path

The provider uses the current Microsoft-supported Python integration:

1. `DefaultAzureCredential` from `azure-identity`
2. `AIProjectClient` from `azure-ai-projects`, configured with `FOUNDRY_PROJECT_ENDPOINT`
3. `get_openai_client()` for an OpenAI-compatible client
4. `responses.create(...)` against the configured deployment name

It does not use API-key authentication, deprecated Azure AI Inference APIs, or hand-written REST transport.

## Configuration

Required only when `AI_PROVIDER=microsoft_foundry`:

```env
AI_PROVIDER=microsoft_foundry
FOUNDRY_PROJECT_ENDPOINT=https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev
FOUNDRY_MODEL_DEPLOYMENT=eci-gpt-54-mini
```

`AI_PROVIDER=mock` continues to work without Foundry settings.

## Verified development environment

The following Foundry resources have been verified manually with an HTTP 200 inference request. Automated tests do **not** call this environment.

| Item | Value |
|---|---|
| Subscription | ECI-Development |
| Resource group | rg-eci-dev |
| Region | Spain Central |
| Foundry resource | eci-foundry-dev-susanta |
| Foundry project | eci-project-dev |
| Project endpoint | `https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev` |
| Deployment | eci-gpt-54-mini |
| Underlying model | gpt-5.4-mini |
| Model version | 2026-03-17 |
| Deployment type | DataZoneStandard |

Phase 16C live-validated **one** selected-message analysis of a real Microsoft Graph mailbox message through the Azure-hosted ECI path (`MicrosoftFoundryProvider`, deployment `eci-gpt-54-mini`). `MockAIProvider` was not used. That is not load testing, throughput certification, model-quality benchmarking, multiple-message certification, Gmail→Foundry cloud certification, or Foundry retry/reconciliation.

## Behavior

The provider receives a `CommunicationRequest` and returns a `CommunicationAnalysisResult` with `provider="microsoft_foundry"`.

It asks the model for:

- summary
- priority
- category
- action items, only when `include_action_items` is true
- draft reply, only when `include_draft_reply` is true

Output is requested as strict JSON Schema through the Responses API `text.format` structured-output path, then validated through the shared `app/providers/common/` analysis contract and mapped onto existing domain models. Malformed JSON or schema-invalid content is rejected explicitly. Azure/OpenAI SDK types never leave the provider package.

Prompt construction lives in `app/providers/common/prompts.py` and is reused by Amazon Bedrock. OpenAI-strict schema normalization stays in `app/providers/microsoft_foundry/output.py`. The model is instructed to operate only on the supplied communication and not fabricate facts.

## Error handling

SDK, network, authentication, and malformed-output failures propagate from the provider. `CommunicationAnalysisService` translates them into `AnalysisFailedError`, which the existing API exception handlers return as a safe `500` response without Azure exception internals.

## Tests

Unit and integration tests mock `DefaultAzureCredential`, `AIProjectClient`, and the OpenAI Responses client. They do not make real Foundry calls and do not require Azure credentials.

## Manual verification

Automated tests stay offline. To verify a real deployment locally (paid inference):

1. `az login`
2. Set `AI_PROVIDER=microsoft_foundry` plus the Foundry endpoint and deployment in `.env`
3. Confirm the signed-in identity has Foundry project inference permission
4. `POST /api/v1/communications/analyze` against a running local API process

Do not run that path from the pytest suite.

## Production deployment

Phase 6C hosts the same Foundry adapter on Azure Container Apps with user-assigned Managed Identity `eci-ca-identity-dev` and `DefaultAzureCredential`. Azure App Service is not used. Phase 16C used that same adapter for one connected-mailbox inference on ACA.

See [Deployment](deployment.md) and the [Azure runbook](../../deployment/azure/README.md).
