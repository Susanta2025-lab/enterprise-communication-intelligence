# Cloud Provider Comparison

ECI compares Microsoft Foundry and Amazon Bedrock behind the same domain `AIProvider` contract. The comparison is architectural, not a claim that one cloud is universally better.

The application, domain, and REST API do not change when the configured provider changes. Both real LLM adapters reuse `app/providers/common/` for the ECI communication-analysis contract (prompt, structured output model, JSON validation, domain mapping, and request flags). Cloud SDKs and schema envelopes stay provider-specific.

| Dimension | Microsoft Foundry | Amazon Bedrock |
|---|---|---|
| ECI provider | `MicrosoftFoundryProvider` | `AmazonBedrockProvider` |
| Configuration name | `microsoft_foundry` | `amazon_bedrock` |
| Initial model | GPT-5.4-mini | Claude Haiku 4.5 |
| SDK | Azure AI Projects / OpenAI client | boto3 |
| API style | Responses API | Converse |
| Structured output | OpenAI-style strict JSON Schema | `outputConfig.textFormat` JSON Schema |
| Local auth | `DefaultAzureCredential` → Azure CLI | boto3 chain → `aws login` credentials |
| Production auth direction | Managed Identity | IAM role / workload identity |
| Region used | Spain Central | `eu-south-2` |
| Shared ECI contract | `providers/common` | `providers/common` |
| Implementation status | Implemented and live-verified through ECI | Implemented and live-verified through ECI |

Neither adapter stores static cloud keys in application Settings.

`MockAIProvider` remains a deterministic offline path and does not use the shared LLM serialization layer.

See:

- [Microsoft Foundry](azure-ai-foundry.md)
- [Amazon Bedrock](amazon-bedrock.md)
- [Authentication](authentication.md)
- [ADR-006](../decisions/ADR-006-azure-ai-foundry.md)
- [ADR-007](../decisions/ADR-007-amazon-bedrock.md)
