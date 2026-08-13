# Cloud Integration

ECI Platform keeps cloud AI SDKs behind the `AIProvider` interface. Application and API code never import vendor clients.

## Current status

| Capability | Status |
|---|---|
| Microsoft Foundry provider | Implemented (`AI_PROVIDER=microsoft_foundry`) |
| Mock provider | Implemented (`AI_PROVIDER=mock`) |
| Amazon Bedrock provider | Not implemented |
| Azure or AWS application hosting | Not implemented |
| Managed Identity in deployed environments | Compatible in code; not yet deployed |

## Microsoft Foundry (implemented)

The first cloud adapter is `MicrosoftFoundryProvider` in `app/providers/microsoft_foundry/`. It uses:

```text
DefaultAzureCredential
        ↓
AIProjectClient
        ↓
get_openai_client()
        ↓
responses.create(...)
```

Verified development infrastructure (no subscription IDs, tenant IDs, or secrets):

| Item | Value |
|---|---|
| Subscription | ECI-Development |
| Resource group | rg-eci-dev |
| Region | Spain Central |
| Foundry resource | eci-foundry-dev-susanta |
| Foundry project | eci-project-dev |
| Deployment | eci-gpt-54-mini |
| Model | gpt-5.4-mini |
| Version | 2026-03-17 |
| Deployment type | DataZoneStandard |

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Authentication](authentication.md)

## Amazon Bedrock (not implemented)

Amazon Bedrock remains a planned future adapter behind the same `AIProvider` contract. See [Amazon Bedrock](amazon-bedrock.md) when that work is requested.

## Deployment (not implemented)

Container images, App Service / App Runner, Key Vault / Secrets Manager, and Monitor / CloudWatch wiring are still future Phase 6 work. See [Deployment](deployment.md).
