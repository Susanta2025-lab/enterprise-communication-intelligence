# Cloud Roadmap

This is the cloud-integration view of Phase 6. It is not a substitute for the phase-by-phase roadmap in [`docs/roadmap/`](../roadmap/README.md).

## Provider integration

| Provider | Status |
|---|---|
| `MockAIProvider` | Implemented |
| `MicrosoftFoundryProvider` | Implemented; live ECI verification completed in Phase 6A |
| `AmazonBedrockProvider` | Implemented; offline tests complete; live ECI verification completed |

## Production deployment

Phase 6C deployment foundation is implemented:

- one Docker image for local mock, Azure Container Apps / Foundry, and ECS Fargate / Bedrock
- Azure compute uses user-assigned Managed Identity for Foundry
- AWS compute uses an ECS Task Role and the ECS container credential provider for Bedrock

See [Deployment](deployment.md).

CI/CD automation is intentionally deferred until the manually validated Azure and AWS deployment paths are stable.

## Secrets and identity

Cloud AI authentication uses platform identity rather than application-stored static keys. Azure Key Vault and AWS Secrets Manager are not implemented.

See [Authentication](authentication.md).

## Observability

Phase 7 is implemented: portable structured logs, Azure Log Analytics plus native Container Apps metrics, and AWS CloudWatch Logs plus standard ECS CPU/memory metrics. Distributed tracing, custom metrics, dashboards, alerts, Application Insights, Container Insights, and OpenTelemetry remain deferred.

See [Observability](observability.md).

## Later enterprise deployment

Production-hardened ingress, private networking, and CI/CD remain later work. Phase 6C validated the manual Azure and AWS paths first.
