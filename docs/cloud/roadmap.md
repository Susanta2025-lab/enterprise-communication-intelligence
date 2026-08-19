# Cloud Roadmap

This is the cloud-integration view of Phase 6 through Phase 8. It is not a substitute for the phase-by-phase roadmap in [`docs/roadmap/`](../roadmap/README.md).

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

## CI/CD

Phase 8 CI/CD is implemented:

- GitHub Actions CI is automatic and tests-only (`contents: read`, no `id-token`)
- Manual `workflow_dispatch` CD deploys `azure` | `aws` | `both` with one build and SHA + `stable` tags
- GitHub OIDC federation to Azure UAMI `eci-github-deploy-dev` and AWS IAM role `eci-github-deploy-dev`
- First verified multi-cloud deploy: commit `dd55327`, identical ACR/ECR digest

Automatic (push/tag) cloud deployment is not enabled.

## Secrets and identity

Cloud AI authentication uses platform identity rather than application-stored static keys. Application-user authentication uses provider-independent OIDC JWT. Live authenticated Azure deployment is verified. AWS real bearer is deferred until TLS. Azure Key Vault and AWS Secrets Manager are not implemented.

See [Authentication](authentication.md).

## Observability

Phase 7 is implemented: portable structured logs, Azure Log Analytics plus native Container Apps metrics, and AWS CloudWatch Logs plus standard ECS CPU/memory metrics. Distributed tracing, custom metrics, dashboards, alerts, Application Insights, Container Insights, and OpenTelemetry remain deferred.

See [Observability](observability.md).

## Later enterprise deployment

Phase 8 is complete. Next is Phase 9 — Persistence & Multi-Tenant/User-Associated Data. Do not implement Phase 9 here. Later: Phase 10 — Enterprise Communication Integrations; Phase 11 — Workflow Automation. AWS persistent HTTPS requires a custom domain and ACM before an ALB is recreated. Private networking, Key Vault, Secrets Manager, and advanced observability remain later work.
