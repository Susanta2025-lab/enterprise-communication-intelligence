# Cloud Roadmap

This is the cloud-integration view of Phase 6. It is not a substitute for the phase-by-phase roadmap in [`docs/roadmap/`](../roadmap/README.md).

## Provider integration

| Provider | Status |
|---|---|
| `MockAIProvider` | Implemented |
| `MicrosoftFoundryProvider` | Implemented; live ECI verification completed in Phase 6A |
| `AmazonBedrockProvider` | Implemented; offline tests complete; live ECI verification completed |

## Production deployment

Not implemented. Future hosted deployment is expected to keep the same provider adapters:

- Azure compute with Managed Identity for Foundry
- AWS compute with an IAM role or other workload identity for Bedrock

See [Deployment](deployment.md).

## Secrets and identity

Cloud AI authentication uses platform identity rather than application-stored static keys. Azure Key Vault and AWS Secrets Manager are not implemented.

See [Authentication](authentication.md).

## Observability

Azure Monitor and Amazon CloudWatch are not implemented. That work belongs to later Phase 6 / Phase 7 scope.

## Future enterprise deployment

Container images, production networking, and operational runbooks remain out of scope until a dedicated hosting phase is requested.
