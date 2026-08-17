# ADR-006: Microsoft Foundry Provider

## Status

Accepted

## Date

Phase 6A (Microsoft Foundry provider)

## Context

Need a production-capable cloud AI provider while preserving provider independence. Communication analysis is already orchestrated through the domain `AIProvider` interface and a configuration-driven factory. The first cloud adapter must not leak Azure types into the application, domain, or REST layers, and must use the current Microsoft-supported Foundry SDK path rather than deprecated inference APIs.

The product name is **Microsoft Foundry**. **Azure AI Foundry** is the former name and is used only as legacy terminology.

## Decision

Use Microsoft Foundry through:

```text
AIProvider
→ MicrosoftFoundryProvider
→ AIProjectClient
→ Responses API
→ Microsoft Entra authentication
```

Select the adapter with `AI_PROVIDER=microsoft_foundry`. Configure the Foundry project endpoint and deployment name through existing Pydantic Settings (`FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_DEPLOYMENT`). Authenticate with `DefaultAzureCredential` so local development can use Azure CLI and Azure Container Apps can use user-assigned Managed Identity without an API key.

## Alternatives Considered

- **API key authentication** — rejected. The current Microsoft SDK path uses Entra ID. API keys would add a stored secret, weaken auditability, and conflict with Managed Identity.
- **Direct raw REST calls** — rejected. Hand-written transport would duplicate SDK auth, retries, and API shape, and would be harder to keep current.
- **Deprecated Azure AI Inference SDK** — rejected. Microsoft's current supported path is `AIProjectClient.get_openai_client()` plus the Responses API.
- **Direct OpenAI/Azure-specific calls from application services** — rejected. That would couple `CommunicationAnalysisService` to a vendor SDK and break the provider-independent architecture.

## Consequences

- `app/providers/microsoft_foundry/` is the only package allowed to import `azure-ai-projects`, `azure-identity`, and the OpenAI client used for Foundry.
- Adding or swapping providers still requires only a factory branch plus a new adapter; application and API code stay unchanged.
- Runtime analysis now has a real network/cloud path when `AI_PROVIDER=microsoft_foundry`. Automated tests remain offline by mocking the SDK.

## Benefits

- Entra ID authentication
- Managed Identity compatibility
- no API-key dependency
- provider isolation
- current Microsoft-supported SDK path

## Trade-offs

- Azure-specific SDK dependency inside the adapter
- cloud/network dependency when this provider is selected
- RBAC requirements on the Foundry project
- token usage cost
- regional/model quota constraints

## Related Components

- `app/providers/microsoft_foundry/provider.py`
- `app/providers/factory.py`
- `app/core/config.py`
- [Provider Abstraction](../architecture/provider-abstraction.md)
- [Microsoft Foundry](../cloud/azure-ai-foundry.md)
- ADR-002 (Provider Abstraction for AI Analysis)
