# Authentication

ECI Platform authenticates to Microsoft Foundry with Microsoft Entra ID. No API key is stored or required by the application.

## Application credential

`MicrosoftFoundryProvider` uses `DefaultAzureCredential` from `azure-identity`. The same application code covers local development and future Azure hosting:

```text
Local development:
DefaultAzureCredential → Azure CLI credential

Future Azure deployment:
DefaultAzureCredential → Managed Identity
```

The provider does not store Azure access tokens, does not accept an API key, and does not log credentials, tokens, request bodies, or secrets.

## Local development

1. Install Azure CLI and run `az login`.
2. Ensure the signed-in identity can invoke the Foundry project deployment.
3. Set:

```env
AI_PROVIDER=microsoft_foundry
FOUNDRY_PROJECT_ENDPOINT=https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev
FOUNDRY_MODEL_DEPLOYMENT=eci-gpt-54-mini
```

`DefaultAzureCredential` then resolves through the Azure CLI session. No key is copied into `.env`.

## Future Azure deployment

When the API is hosted on Azure, assign a Managed Identity to the compute resource and grant it Foundry project access. `DefaultAzureCredential` should then resolve to that identity without changing provider code.

Key Vault and production secret management are not implemented in this phase. Foundry access uses Entra ID rather than a stored model key.

## What is not implemented

- API-key authentication for Foundry
- Application-level user authentication/authorization for the REST API
- AWS IAM / Bedrock authentication
- Storing or caching Entra tokens in application code
