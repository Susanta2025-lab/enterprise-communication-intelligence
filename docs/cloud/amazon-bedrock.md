# Amazon Bedrock Integration

This document describes the implemented Amazon Bedrock provider. Live inference through the ECI application has been verified.

## Purpose

`AmazonBedrockProvider` implements the existing domain `AIProvider` contract so communication analysis can run on Amazon Bedrock without changing the application, domain, or REST layers.

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
              Bedrock Runtime Converse
```

Azure SDK types stay in `app/providers/microsoft_foundry/`. boto3 types stay in `app/providers/amazon_bedrock/`.

## Current Implementation

| Item | Value |
|---|---|
| Provider class | `AmazonBedrockProvider` |
| Configuration name | `amazon_bedrock` |
| SDK | `boto3[crt]>=1.41.0` |
| Runtime service | `bedrock-runtime` |
| API | Converse |
| Structured output | `outputConfig.textFormat` JSON Schema |
| Initial model | Claude Haiku 4.5 |
| Initial model ID | `eu.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Region | `eu-south-2` (Europe / Spain) |
| Status | Implemented, offline-tested, and live-verified through ECI |

The model ID and region are configurable. The Haiku 4.5 inference profile is the current baseline, not a permanently fixed model.

## Provider Flow

```text
CommunicationRequest
        ↓
common SYSTEM_PROMPT + build_user_prompt()
        ↓
AmazonBedrockProvider
        ↓
boto3 bedrock-runtime
        ↓
Converse
        ↓
outputConfig.textFormat JSON Schema
        ↓
Bedrock-specific response extraction
        ↓
parse_analysis_output()
        ↓
to_communication_analysis()
        ↓
CommunicationAnalysisResult(provider="amazon_bedrock")
```

## Configuration

Required only when `AI_PROVIDER=amazon_bedrock`:

```env
AI_PROVIDER=amazon_bedrock
BEDROCK_REGION=eu-south-2
BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

`AI_PROVIDER=mock` and `AI_PROVIDER=microsoft_foundry` continue to work without Bedrock settings.

ECI Settings do not include `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, or `AWS_PROFILE`.

## Authentication

The adapter uses boto3's standard credential chain. It does not hard-code an AWS profile and does not construct `boto3.Session(profile_name=...)`.

```text
Local development:
ECI → boto3 credential chain → externally selected AWS CLI profile
     → aws login temporary credentials

Future AWS deployment:
ECI → boto3 credential chain → IAM role / workload credentials
```

Cloud/provider authentication is separate from ECI application-user authentication, which is not implemented.

## Converse API

The provider calls Bedrock Runtime `converse` with:

- `modelId` from `BEDROCK_MODEL_ID`
- `system` containing the shared ECI `SYSTEM_PROMPT`
- a user message containing `build_user_prompt(request)`
- `outputConfig.textFormat` requesting JSON Schema structured output

It does not use `invoke_model`, streaming, tool use, or a provider-specific Anthropic request body.

## Structured Output

The JSON Schema is generated from the shared `AnalysisOutput` model in `app/providers/common/output.py` and supplied to Converse as a JSON string. Bedrock-specific code extracts the first usable text block from the Converse response. Shared code then:

1. parses JSON
2. validates with Pydantic
3. maps onto domain models
4. enforces `include_action_items` and `include_draft_reply`

OpenAI-strict schema normalization remains Foundry-specific and is not reused here.

Action-item `due_at` is `datetime | None` on the shared `AnalysisActionItemOutput` model. The prompt asks the model to return an ISO-8601 date-time only when it can be determined from the supplied communication. Relative or ambiguous dates such as "Friday" must be `null`; they are not invented into an exact datetime.

## Model Configuration

Claude Haiku 4.5 through the EU inference profile is the initial baseline because independent CLI verification confirmed Converse structured output in `eu-south-2`. Operators may change `BEDROCK_MODEL_ID` without changing provider code.

## Testing Strategy

Automated tests stay offline. They inject a mocked Bedrock Runtime client or patch `boto3.client`. They do not call AWS, do not require `aws login`, and do not resolve live credentials.

## Current Verification Status

```text
independent AWS/Bedrock capability verification: complete
offline automated ECI coverage: complete (218 tests passing)
real application-level ECI → Bedrock verification: complete
```

The application-level test confirmed boto3 credential resolution, Bedrock Runtime access, Converse, structured JSON, ECI common parsing/mapping, action-item handling, and REST serialization:

```text
REST API
→ CommunicationAnalysisService
→ AIProvider
→ AmazonBedrockProvider
→ boto3 credential chain
→ Amazon Bedrock Runtime
→ Converse API
→ Claude Haiku 4.5
→ JSON Schema structured output
→ shared common parser/domain mapping
→ REST response
```

The successful response used `provider = "amazon_bedrock"` and returned a valid summary, priority, category, action items, draft reply, and `message_id`. A live request with `include_action_items = true`, `include_draft_reply = true`, and a relative "by Friday" deadline returned two action items with `due_at = null`.

## Production Deployment Direction

Provider integration is not the same as production hosting. Future AWS deployment should use an IAM role or other workload identity through the same boto3 credential chain. App Runner, Secrets Manager, and CloudWatch are not implemented.
