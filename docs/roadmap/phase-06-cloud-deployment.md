# Phase 06 Cloud Deployment

## Objective

Introduce production-capable cloud AI integration and a provider-independent deployment foundation while preserving the architecture established in Phases 1–5.

## Business Value

- Enables real model inference for communication analysis without changing the domain, application, or REST contracts.
- Keeps local/offline development available through `MockAIProvider`.
- Uses Microsoft Entra ID so local Azure CLI login and Azure Container Apps Managed Identity share the same application code.
- Uses boto3's standard credential chain so local `aws login` credentials and the ECS Task Role share the same Bedrock adapter.
- Uses one Docker image across local mock, Azure Foundry, and AWS Bedrock.

## Status

Phase 6 is complete:

- **6A is implemented and live-verified:** `MicrosoftFoundryProvider` behind the existing `AIProvider` interface.
- **6B is implemented, offline-tested, and live-verified:** `AmazonBedrockProvider` behind the same interface.
- **6C is implemented and live-verified:** one Docker image on Azure Container Apps and Amazon ECS Fargate.

Not part of Phase 6 (later work):

- Azure Key Vault or AWS Secrets Manager
- Azure Monitor or CloudWatch metrics, tracing, and dashboards (Phase 7)
- CI/CD automation

## Deliverables (6A)

- `app/providers/microsoft_foundry/` — `MicrosoftFoundryProvider`
- Settings for `FOUNDRY_PROJECT_ENDPOINT` and `FOUNDRY_MODEL_DEPLOYMENT`
- Factory selection via `AI_PROVIDER=microsoft_foundry`
- Offline unit tests with mocked Foundry SDK clients
- Cloud and architecture documentation for the implemented adapter
- ADR-006 Microsoft Foundry Provider

## Deliverables (6B)

- `app/providers/common/` — shared LLM analysis contract
- `app/providers/amazon_bedrock/` — `AmazonBedrockProvider`
- Settings for `BEDROCK_REGION` and `BEDROCK_MODEL_ID`
- Factory selection via `AI_PROVIDER=amazon_bedrock`
- Offline unit and integration tests with mocked Bedrock Runtime clients
- Cloud and architecture documentation for the implemented adapter
- ADR-007 Amazon Bedrock Provider
- Live ECI → Amazon Bedrock verification through `POST /api/v1/communications/analyze`

## Deliverables (6C)

- Provider-independent `Dockerfile`, `docker-compose.yml`, and `.dockerignore`
- Local Docker verification (non-root, health check, mock analyze)
- Azure Container Apps + ACR + user-assigned Managed Identity runbook and live Foundry verification
- Amazon ECS Fargate + ECR + ECS Task Role runbook and live Bedrock verification
- Deployment architecture, identity, security, and cost-control documentation

## Tasks

- [x] Implement `MicrosoftFoundryProvider` against the existing `AIProvider` contract
- [x] Authenticate with `DefaultAzureCredential` (no API key)
- [x] Call Microsoft Foundry through `AIProjectClient` → `get_openai_client()` → `responses.create(...)`
- [x] Keep mock provider working without Foundry configuration
- [x] Add deterministic offline tests
- [x] Document verified Foundry development infrastructure without secrets
- [x] Extract shared LLM analysis contract into `app/providers/common/`
- [x] Implement `AmazonBedrockProvider` against the existing `AIProvider` contract
- [x] Authenticate with the boto3 credential chain (no static AWS keys in Settings)
- [x] Call Amazon Bedrock through Bedrock Runtime Converse and JSON Schema structured output
- [x] Add deterministic offline Bedrock tests
- [x] Final live ECI → Amazon Bedrock verification
- [x] Container and cloud hosting (Azure Container Apps and ECS Fargate)

## Architectural Decisions

- Cloud SDKs stay inside the provider adapter.
- Foundry and Bedrock share the ECI communication-analysis prompt, structured output model, JSON validation, and domain mapping.
- OpenAI-strict schema normalization stays Foundry-specific. Converse `outputConfig.textFormat` stays Bedrock-specific.
- Foundry settings are required only when `AI_PROVIDER=microsoft_foundry`.
- Bedrock settings are required only when `AI_PROVIDER=amazon_bedrock`.
- One image for all environments; cloud differences are environment and workload identity.
- Azure application identity is user-assigned Managed Identity. AWS application identity is the ECS Task Role, not the Task Execution Role.

See [ADR-006](../decisions/ADR-006-azure-ai-foundry.md) and [ADR-007](../decisions/ADR-007-amazon-bedrock.md).

## Acceptance Criteria

- [x] `MockAIProvider` still works
- [x] `MicrosoftFoundryProvider` implements `AIProvider`
- [x] Factory selects Microsoft Foundry via configuration
- [x] `AmazonBedrockProvider` implements `AIProvider`
- [x] Factory selects Amazon Bedrock via configuration
- [x] No API key or static AWS key is required in ECI Settings
- [x] Domain/application/API layers remain provider-independent
- [x] Automated tests make no real Azure or AWS network calls
- [x] Live ECI → Amazon Bedrock verification
- [x] Phase 6C deployment foundation (same image on Azure Container Apps and ECS Fargate)

## Risks and Trade-offs

- Foundry and Bedrock inference have network, identity, quota, and token-cost dependencies.
- Automated tests cannot prove live model quality; a manual paid inference check remains an operator step for future environments.
- Different models may classify semantically similar messages differently until prompt calibration is requested.
- Phase 6C verification ingress is operator `/32` only. Direct Fargate public-IP access is not production ingress architecture.

## Verification (6B)

- `python -m ruff check .`: passed
- `python -m pytest`: passed (`218 passed`), offline, with no AWS or Azure calls
- Live ECI → Amazon Bedrock: `POST /api/v1/communications/analyze` returned `provider = "amazon_bedrock"` with a valid summary, priority, category, action items, draft reply, and `message_id`

## Verification (6C)

- Local Docker image verified (Python 3.12, non-root, HEALTHCHECK, mock analyze)
- Same image deployed to Azure Container Apps; live analyze returned `provider = "microsoft_foundry"`
- Same image deployed to ECS Fargate; live analyze returned `provider = "amazon_bedrock"`
- AWS service scaled to `desiredCount=0` after verification
- Azure remains deployed with operator-restricted ingress

## Lessons Learned

Provider integration and the deployment foundation are complete for Foundry and Bedrock. Remaining work is secrets management, production-hardened ingress, CI/CD, and Phase 7 observability.

## Next Phase

Phase 7 – Observability.
