# Cloud Integration

ECI Platform keeps cloud AI SDKs behind the `AIProvider` interface. Application and API code never import vendor clients.

## Current status

| Capability | Status |
|---|---|
| Mock provider | Implemented (`AI_PROVIDER=mock`) |
| Microsoft Foundry provider | Implemented (`AI_PROVIDER=microsoft_foundry`) |
| Amazon Bedrock provider | Implemented and live-verified (`AI_PROVIDER=amazon_bedrock`) |
| Azure or AWS application hosting | Not implemented |
| Managed Identity / IAM roles in deployed environments | Compatible in adapter design; not yet deployed |

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Amazon Bedrock](amazon-bedrock.md)
- [Authentication](authentication.md)
- [Provider comparison](comparison.md)
- [Cloud roadmap](roadmap.md)
- [Deployment](deployment.md)

## Microsoft Foundry (implemented)

`MicrosoftFoundryProvider` in `app/providers/microsoft_foundry/` uses:

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

## Amazon Bedrock (implemented and live-verified)

`AmazonBedrockProvider` in `app/providers/amazon_bedrock/` uses:

```text
boto3 standard credential chain
        ↓
bedrock-runtime
        ↓
converse(...)
        ↓
outputConfig.textFormat JSON Schema
```

Current configurable baseline:

| Item | Value |
|---|---|
| Region | `eu-south-2` (Europe / Spain) |
| Initial model | Claude Haiku 4.5 |
| Model ID | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` |

Independent CLI Bedrock capability was verified before implementation. Offline automated tests are complete. The real ECI REST path to Bedrock has been live-verified.

## Shared LLM analysis contract

Microsoft Foundry and Amazon Bedrock share `app/providers/common/` for ECI prompt construction, structured-output models, JSON validation, and domain mapping. That package is not a generic LLM framework. `MockAIProvider` does not use it.

## Deployment (not implemented)

Container images, App Service / App Runner, Key Vault / Secrets Manager, and Monitor / CloudWatch wiring remain future Phase 6 work. See [Deployment](deployment.md).
