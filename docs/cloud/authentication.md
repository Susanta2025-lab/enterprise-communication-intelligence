# Authentication

ECI authenticates to cloud AI platforms through each provider's standard identity chain. The application does not store static cloud keys. This is cloud/provider authentication, not ECI application-user authentication. REST API user login and authorization are not implemented.

## Microsoft Foundry

`MicrosoftFoundryProvider` uses `DefaultAzureCredential` from `azure-identity`. The same application code covers local development and future Azure hosting:

```text
Local Azure:
DefaultAzureCredential → Azure CLI credential

Future Azure deployment:
DefaultAzureCredential → Managed Identity
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

### Future Azure deployment

When the API is hosted on Azure, assign a Managed Identity to the compute resource and grant it Foundry project access. `DefaultAzureCredential` should then resolve to that identity without changing provider code.

## Amazon Bedrock

`AmazonBedrockProvider` uses boto3's standard credential chain. The application does not read `AWS_PROFILE` itself and does not hard-code a profile name.

```text
Local AWS:
ECI → boto3 standard credential chain
    → externally selected AWS CLI profile
    → aws login temporary credentials

Future AWS deployment:
ECI → boto3 standard credential chain
    → IAM role / workload credentials
```

ECI Settings do not include `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, or `AWS_PROFILE`.

### Local Bedrock development

1. Authenticate with the AWS CLI using `aws login` for the profile selected in the shell environment.
2. Set:

```env
AI_PROVIDER=amazon_bedrock
BEDROCK_REGION=eu-south-2
BEDROCK_MODEL_ID=eu.anthropic.claude-haiku-4-5-20251001-v1:0
```

boto3 then resolves credentials from the environment. No AWS key is copied into `.env`.

### Future AWS deployment

When the API is hosted on AWS, attach an IAM role (or equivalent workload identity) that can invoke Bedrock Runtime in the configured region. The same provider code should resolve those credentials through boto3 without an application-stored key.

## Shared rule

Neither cloud adapter stores static access keys in ECI configuration.

Key Vault, Secrets Manager, and production secret management are not implemented in this phase.

## What is not implemented

- API-key authentication for Foundry
- Application-level user authentication/authorization for the REST API
- Storing or caching Entra tokens or AWS credentials in application code
- Hard-coded AWS profile selection
