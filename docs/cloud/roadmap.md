# Cloud Roadmap

This is the cloud-integration view of Phase 6 through completed Phase 14. It is not a substitute for the phase-by-phase roadmap in [`docs/roadmap/`](../roadmap/README.md).

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

Cloud AI authentication uses platform identity rather than application-stored static keys. Application-user authentication uses provider-independent OIDC JWT. Live authenticated Azure deployment is verified. AWS real bearer is deferred until TLS. Azure Key Vault and AWS Secrets Manager are implemented as mailbox OAuth credential stores (Phase 13E). They are not `DATABASE_URL` secret backends.

See [Authentication](authentication.md).

## Persistence

Phase 9 selects cloud-portable PostgreSQL with ephemeral CI proof. Phase 16B provisioned Azure Database for PostgreSQL Flexible Server. Phase 16D provisioned Amazon RDS `eci-pg-dev`. Shared cross-cloud databases and dual standing managed databases remain rejected. After 16F both servers are **Stopped**. Temporary stop is not indefinite; each provider may automatically restart the database after its permitted stop interval (AWS currently 7 days). See [PostgreSQL persistence](persistence.md) and [ADR-014](../decisions/ADR-014-cloud-postgresql-deployment-strategy.md).

## Observability

Phase 7 is implemented: portable structured logs, Azure Log Analytics plus native Container Apps metrics, and AWS CloudWatch Logs plus standard ECS CPU/memory metrics. Distributed tracing, custom metrics, dashboards, alerts, Application Insights, Container Insights, and OpenTelemetry remain deferred.

See [Observability](observability.md).

## Later enterprise deployment

Phase 8 is complete. Phase 9 persistence is complete at the application and CI-proof level. Phase 10 communication connectors are complete on the local/application side: vendor-neutral `CommunicationConnector`, Gmail and Microsoft Graph read-only REST adapters, user-owned `connector_accounts`, and controlled local live adapter checks that stopped at `CommunicationMessage`.

Cloud runtimes still do **not** provide:

- background mailbox sync
- automatic replies from cloud-hosted ECI
- workers, webhooks, search, or attachments
- a 2×2×2 cloud × mailbox × AI matrix (Gmail on Azure or Graph on AWS were not required)
- live Send as a standing Phase 16 exit criterion

Phase 16C live-validated Azure-hosted Microsoft Graph delegated OAuth, Azure Key Vault credential durability across an ACA same-revision recycle, one `MicrosoftFoundryProvider` selected-message analysis, and explicit Propose → Approve, stopping before Send.

Phase 16D certified AWS CloudFront SPA/API HTTPS hosting only. Phase 16E certified AWS Gmail → Bedrock, including one historical Send. Phase 16F re-validated Azure Outlook connect-another → Foundry and AWS Gmail multi-account → Bedrock, both stopping before Send.

Environment-backed `CommunicationCredentialResolver` and user-approved Graph/Gmail execute exist in the application. Bounded mailbox listing and selected-message analyze HTTP exist in the application and were live-validated locally with `MockAIProvider`. The frozen Phase 16 matrix is complete: Azure Graph → Foundry; AWS Gmail → Bedrock.

Controlled live adapter verification in Phase 10 was local and stopped at `CommunicationMessage`. Phase 14 locally live-validated list → selected-message analyze.

Phase 11 workflow automation is application-layer work documented in [Phase 11](../roadmap/phase-11-workflow-automation.md). Phase 12 adds user-approved Gmail and Microsoft Graph reply execution through `POST /api/v1/workflow-actions/{action_id}/execute`. Phase 13 implements delegated Gmail/Microsoft OAuth, disconnect/reauthorize HTTP, Azure Key Vault and AWS Secrets Manager mailbox credential stores, and PostgreSQL advisory-lock coordination. Phase 14 adds `communications:read`, bounded listing, and selected-message analyze. Local Google/Microsoft consent and explicitly approved replies, live Key Vault/Secrets Manager store validation, and local mailbox list→analyze are recorded on the phase roadmaps. Azure-hosted Graph mailbox OAuth and Graph → Foundry analyze → Propose → Approve were live-validated in Phase 16C and 16F and stopped before Send. AWS Gmail → Bedrock was live-validated in Phase 16E (historical Send) and Phase 16F (stop before Send). Automatic replies remain later work. ALB-native HTTPS still requires a custom domain and ACM (ADR-010). Phase 16A froze CloudFront default HTTPS in front of an HTTP ALB so browser bearer tokens do not wait on a custom domain; Phase 16D created that AWS path. Phase 16B provisioned Azure Static Web Apps, Azure PostgreSQL Flexible Server, and then-current ACA with Key Vault selected. Phase 16D provisioned private S3 + CloudFront SPA, API CloudFront → HTTP ALB → ECS, and Amazon RDS. Current retained lineage is `3fa3412` / schema `16f0001` / AWS task definition `eci-api-dev:8`. Compute is scaled to zero. Both managed databases are Stopped; temporary stop may auto-restart after the provider interval. `DATABASE_URL` on ECS is an injected secret reference, not an application-read of the mailbox Secrets Manager namespace. Private networking hardening, optional temporary IAM cleanup, and advanced observability remain later production work. See [Phase 16](../roadmap/phase-16-cloud-browser-multicloud-validation.md) and [ADR-026](../decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md).
