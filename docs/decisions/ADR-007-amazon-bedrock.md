# ADR-007: Amazon Bedrock Provider

## Status

Accepted

The decision is implemented. Offline tests pass. Live ECI → Amazon Bedrock verification has succeeded.

## Date

Phase 6B (Amazon Bedrock provider)

## Context

ECI needed a second real cloud AI provider to validate the provider-independent architecture and compare Microsoft Foundry with Amazon Bedrock. Communication analysis is already orchestrated through the domain `AIProvider` interface, a configuration-driven factory, and a shared LLM analysis contract extracted in Prompt 2 (`app/providers/common/`).

The second adapter must not leak AWS types into the application, domain, or REST layers. Authentication must use the standard boto3 credential chain rather than application-stored access keys or a hard-coded AWS profile.

## Decision

Use Amazon Bedrock through:

```text
AIProvider
→ AmazonBedrockProvider
→ boto3 bedrock-runtime
→ Converse API
→ outputConfig.textFormat JSON Schema
```

Select the adapter with `AI_PROVIDER=amazon_bedrock`. Configure region and model ID through Pydantic Settings (`BEDROCK_REGION`, `BEDROCK_MODEL_ID`). Authenticate with boto3's standard credential chain so local development can use `aws login` temporary credentials from an externally selected CLI profile, and ECS Fargate can use the ECS container credential provider and Task Role without changing provider code.

The initial baseline model is Claude Haiku 4.5 through the EU inference profile `eu.anthropic.claude-haiku-4-5-20251001-v1:0` in `eu-south-2`. The model ID remains fully configurable.

Before implementing Bedrock, extract the ECI LLM business-analysis contract into:

```text
app/providers/common/output.py
app/providers/common/prompts.py
```

Cloud transport, SDK clients, and schema envelopes remain provider-specific. Shared code covers the analysis prompt, structured output model, JSON validation, domain mapping, and request feature flags.

## Alternatives Considered

- **Package location `app/providers/aws/` or `app/providers/aws/bedrock/`** — rejected. Phase 6A placed the Azure adapter at `microsoft_foundry/` rather than under `azure/`. Bedrock follows the same product/service-oriented layout at `app/providers/amazon_bedrock/`.
- **Duplicated Foundry output/prompt implementation inside Bedrock** — rejected. That would create two copies of the same ECI communication-analysis contract.
- **Hard-coded AWS profile or static access keys in Settings** — rejected. The application must not store `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, or `AWS_PROFILE`, and must not hard-code `eci-dev`.
- **`invoke_model` or a provider-specific Anthropic payload** — rejected for the baseline. Converse is the Bedrock Runtime API used by this adapter.
- **Permanently fixing Claude Haiku 4.5 in provider logic** — rejected. Independent CLI verification confirmed Converse structured output for that model, so it is the initial configurable baseline rather than a coded constant.

## Consequences

- `app/providers/amazon_bedrock/` is the only package allowed to import boto3 for Bedrock Runtime.
- Adding Bedrock required a factory branch, Settings fields, and the Bedrock adapter; `CommunicationAnalysisService` and `AIProvider` stayed unchanged.
- Automated tests remain offline by injecting a mocked runtime client or patching `boto3.client`.
- Live ECI → Bedrock verification has been completed manually. pytest does not execute that path.

## Benefits

- second real cloud provider behind the same domain contract
- cloud-neutral application and domain architecture validated
- shared ECI analysis contract reused by Foundry and Bedrock
- identity-based authentication direction with no static keys in ECI
- configurable model ID and region
- offline-testable provider adapter

## Trade-offs

- provider-specific schema envelopes still exist (OpenAI-strict vs Converse `outputConfig`)
- model behavior may differ across providers
- priority classification may require later prompt calibration
- additional AWS SDK dependency (`boto3[crt]`)
- secrets management and observability remain later work; Phase 6C later added ECS Fargate hosting

## Related Components

- `app/providers/amazon_bedrock/provider.py`
- `app/providers/amazon_bedrock/output.py`
- `app/providers/common/output.py`
- `app/providers/common/prompts.py`
- `app/providers/factory.py`
- `app/core/config.py`
- [Provider Abstraction](../architecture/provider-abstraction.md)
- [Amazon Bedrock](../cloud/amazon-bedrock.md)
- ADR-002 (Provider Abstraction for AI Analysis)
- ADR-006 (Microsoft Foundry Provider)
