# Authentication

ECI has six identity paths. They must not be mixed.

1. **Application user → Microsoft Entra ID → JWT → ECI API.** Provider-independent OIDC JWT validation at the API boundary. The first live identity provider is a single-tenant Microsoft Entra ID resource application. ECI does not use Easy Auth or a Cognito SDK. Phase 9 maps verified `(issuer, subject)` to an opaque internal user UUID for ownership only; that is not a login user database and not SaaS tenancy. The caller's OIDC token does not authenticate to PostgreSQL. See [API Overview](../api/overview.md), [ADR-009](../decisions/ADR-009-application-user-authentication.md), and [ADR-013](../decisions/ADR-013-external-identity-mapping-and-user-owned-data.md).
2. **Azure workload → Microsoft Foundry.** Container Apps user-assigned identity `eci-ca-identity-dev` through `DefaultAzureCredential`.
3. **AWS workload → Amazon Bedrock.** ECS Task Role `eci-bedrock-task-role-dev` through boto3's standard credential chain.
4. **GitHub Actions → Azure / AWS deploy identities.** GitHub OIDC federation to Azure user-assigned managed identity `eci-github-deploy-dev` and AWS IAM role `eci-github-deploy-dev`. Same display name, different cloud object types. These identities must not receive Foundry or Bedrock invoke permissions. GitHub OIDC subjects use the immutable unique-ID format (`repo:OWNER@OWNER-ID/REPO@REPO-ID:environment:…`).
5. **ECI runtime → PostgreSQL database identity.** Application contract is `DATABASE_URL` when persistence is configured. Runtime DML credentials should be separate from migration DDL credentials. No managed Azure or AWS database is provisioned in Phase 9, so this cloud identity remains future until a colocated database exists. See [PostgreSQL persistence](persistence.md).
6. **Mailbox credentials → Gmail / Microsoft Graph access tokens.** Opaque `ConnectorAccount.credential_ref` is resolved by `CommunicationCredentialResolver` into an on-demand `AccessTokenProvider`. Local/development and legacy execute composition use environment-backed token material (`ECI_COMMUNICATION_CREDENTIAL_<PROVIDER>_<NORMALIZED_REF>_ACCESS_TOKEN`). Phase 13B adds a provider-neutral `CommunicationCredentialStore` and a refreshable resolver that acquires tokens only when the callable is invoked. Phase 13C adds Google mailbox OAuth: `POST /api/v1/connector-accounts/gmail/authorize` (`communications:connect`) and unauthenticated `GET /api/v1/oauth/callbacks/gmail`. Google identity is the verified OIDC `sub`. Phase 13D adds Microsoft mailbox OAuth: `POST /api/v1/connector-accounts/microsoft_graph/authorize` (`communications:connect`) and unauthenticated `GET /api/v1/oauth/callbacks/microsoft_graph`. Microsoft identity is the verified ID-token `{tid}:{oid}`. Refreshable material lives in the credential store, not PostgreSQL. Development/test composition may share one in-memory store in-process; that store is not production credential storage. `APP_ENV=production` enables Gmail and Microsoft connect only when `CREDENTIAL_STORE_BACKEND` is `azure_key_vault` or `aws_secrets_manager` with complete non-secret identifiers. Production never uses the in-memory store. This is not the ECI API JWT, not AI workload identity, and not database identity. Analyze, workflow, send, and connect remain distinct permissions.

The rest of this document describes application-user OIDC and cloud/provider authentication. Deployment OIDC is summarized in [Deployment](deployment.md).

## Application-user authentication

```text
Client
→ Microsoft Entra ID
→ access token (JWT)
→ ECI TokenValidator
→ permission communications:analyze
→ POST /api/v1/communications/analyze
```

Analyze and history require `communications:analyze`. Workflow proposal and approval require `communications:workflow`. Execute requires `communications:send`. Gmail and Microsoft mailbox connect require `communications:connect`. These are distinct capabilities; `OIDC_REQUIRED_PERMISSION` remains the analyze permission. Least privilege: a workflow-only token cannot send mail, a send-only token cannot create or approve a workflow action, and none of those imply mailbox OAuth connect. `communications:workflow` does not authorize external sending. The Google and Microsoft callbacks are not ECI login and do not use the API bearer token.

Live Entra configuration is conceptual here (placeholders only; no tenant or client IDs):

- Resource application: `eci-api-auth-dev`
- `requestedAccessTokenVersion=2`
- Application ID URI: `api://<ECI_API_CLIENT_ID>`
- One delegated scope: `communications:analyze` (expected token claim: `scp`)

Runtime settings are identifiers and metadata, not secrets:

```env
AUTH_MODE=oidc
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_AUDIENCE=<ECI_API_CLIENT_ID>
OIDC_JWKS_URL=https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys
OIDC_REQUIRED_PERMISSION=communications:analyze
```

A DEV-ONLY public client (`eci-auth-verifier-dev`) exists for interactive verification. It has no client secret. It is retained as test identity infrastructure with only the ECI delegated permission `communications:analyze`. It is not a runtime or deploy identity. Do not store Entra client secrets in ECI Settings, the container image, or GitHub.

`APP_ENV=production` requires `AUTH_MODE=oidc`. Health and readiness remain public. Production OpenAPI routes stay disabled.

Azure authorized inference was verified over Container Apps HTTPS with a real bearer token. Never send a real application-user bearer token over the AWS HTTP verification path. AWS real-bearer authorized inference is deferred until domain/ACM TLS exists.

## Microsoft Foundry

`MicrosoftFoundryProvider` uses `DefaultAzureCredential` from `azure-identity`. The same application code covers local development and Azure Container Apps:

```text
Local Azure:
DefaultAzureCredential → Azure CLI credential

Azure Container Apps:
DefaultAzureCredential
→ AZURE_CLIENT_ID selects user-assigned Managed Identity
→ Foundry User
→ Microsoft Foundry
```

The provider does not store Azure access tokens, does not accept an API key, and does not log credentials, tokens, request bodies, or secrets.

### Local Foundry development

1. Install Azure CLI and run `az login`.
2. Ensure the signed-in identity can invoke the Foundry project deployment.
3. Set:

```env
AI_PROVIDER=microsoft_foundry
FOUNDRY_PROJECT_ENDPOINT=https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev
FOUNDRY_MODEL_DEPLOYMENT=eci-gpt-54-mini
```

`DefaultAzureCredential` then resolves through the Azure CLI session. No key is copied into `.env`.

### Azure Container Apps

The Container App uses user-assigned identity `eci-ca-identity-dev` with the Foundry User role. `AZURE_CLIENT_ID` selects that identity for `DefaultAzureCredential()`. No client secret or Foundry API key is used.

See [Deployment](deployment.md) and the [Azure runbook](../../deployment/azure/README.md).

## Amazon Bedrock

`AmazonBedrockProvider` uses boto3's standard credential chain. The application does not read `AWS_PROFILE` itself and does not hard-code a profile name.

```text
Local AWS:
ECI → boto3 standard credential chain
    → externally selected AWS CLI profile
    → aws login temporary credentials

ECS Fargate:
ECI → boto3 standard credential chain
    → ECS container credential provider
    → ECS Task Role
    → bedrock:InvokeModel
```

ECI Settings do not include `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, or `AWS_PROFILE`.

Fargate credentials are not EC2 instance metadata.

### Local Bedrock development

1. Authenticate with the AWS CLI using `aws login` for the profile selected in the shell environment.
2. Set:

```env
AI_PROVIDER=amazon_bedrock
BEDROCK_REGION=eu-south-2
BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

boto3 then resolves credentials from the environment. No AWS key is copied into `.env`.

### ECS Fargate

The application identity is Task Role `eci-bedrock-task-role-dev` (inline policy `eci-bedrock-invoke-dev`, `bedrock:InvokeModel` only). Task Execution Role `eci-ecs-execution-role-dev` pulls from ECR and writes CloudWatch `awslogs`. Those roles are not merged. The container does not receive AWS access keys or `AWS_PROFILE`.

Operator CloudWatch metric-read permissions (`cloudwatch:ListMetrics`, `cloudwatch:GetMetricStatistics`) belong to IAM user `eci-developer` (CLI profile `eci-dev`). They are not on the application task role or the execution role. Azure Log Analytics configuration does not introduce application credentials.

See [Deployment](deployment.md) and the [AWS runbook](../../deployment/aws/README.md).

## Shared rule

Neither cloud adapter stores static access keys in ECI configuration.

Mailbox OAuth secrets in production are stored in Azure Key Vault or AWS Secrets Manager. Workload identity is `DefaultAzureCredential` (Container Apps managed identity) or the ECS task role. Settings hold only non-secret identifiers (`AZURE_KEY_VAULT_URL`, `AWS_SECRETS_MANAGER_REGION`, namespace). Cloud mutations are serialized with PostgreSQL transaction-scoped advisory locks keyed by the opaque `credential_ref`; PostgreSQL stores coordination only, not OAuth secret or token material. Azure Key Vault does not provide linearizable CAS. AWS retains native version/stage compare-and-set in addition. Least privilege: Key Vault secret get/set/delete on the ECI prefix; Secrets Manager `CreateSecret`, `GetSecretValue`, `PutSecretValue`, `UpdateSecretVersionStage`, `DescribeSecret`, and `DeleteSecret` on the `eci/mailbox-oauth/*` name/ARN boundary. Do not grant `ListSecrets`, `SecretsManagerFullAccess`, subscription Owner, or `AdministratorAccess`. Phase 13E live-validated the Azure and AWS stores through the factory and PostgreSQL coordinator against the existing development Key Vault and the ECI developer AWS identity; that is store validation, not cloud-hosted Gmail/Graph OAuth certification. Environment-backed mailbox tokens remain local/dev only.

## What is not implemented

- API-key authentication for Foundry
- Password login or a session store for the REST API. Phase 9 stores opaque `users.id` plus `issuer`/`subject` for ownership only.
- Storing or caching Entra tokens or AWS credentials in application code
- Hard-coded AWS profile selection
- AWS real-bearer authorized requests over TLS (deferred until domain/ACM)
- Live Google Cloud project certification (consent screen, Gmail API enablement, test users, browser consent). Google OAuth code exists; live validation is an external operator step.
- Live Microsoft Entra mailbox consent certification (web redirect URI, Mail.Read, Mail.Send, browser consent). Microsoft OAuth code exists; live validation is an external operator step.
