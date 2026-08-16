# Deployment

Cloud application hosting is not implemented. ECI currently runs as a local FastAPI process. Provider integration (Microsoft Foundry and Amazon Bedrock) is not the same as production deployment.

## Planned directions

These are intended future hosting paths. They are not designed or implemented here.

```text
Azure → future hosted deployment + Managed Identity
AWS   → future hosted deployment + IAM role / workload identity
```

The existing adapters already authenticate through platform credential chains (`DefaultAzureCredential` and boto3), so a later hosting phase should not need a second application-level key store for model inference.

## Not implemented

- Docker images and Compose runtime
- Azure App Service / AWS App Runner
- Azure Key Vault / AWS Secrets Manager
- Azure Monitor / Amazon CloudWatch
- production networking, scaling, or CI/CD deployment pipelines

Placeholder directories exist under `deployment/docker/`, `deployment/azure/`, and `deployment/aws/` (`.gitkeep` only).

See [Cloud Roadmap](roadmap.md) and [Authentication](authentication.md).
