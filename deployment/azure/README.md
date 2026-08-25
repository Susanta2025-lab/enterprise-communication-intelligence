# Azure Container Apps — Phase 6C Runbook

Operator runbook for deploying the already verified ECI Docker image to Azure Container Apps.

**Status:** Prompt 5 live deployment completed. Phase 7B attached Log Analytics and deployed image `eci-api:phase7a-5f4f5f8` (revision `eci-api-dev--0000001`). `eci-api-dev` remains in `rg-eci-deploy-dev` with operator `/32` ingress and min replicas 0. Do not re-run mutating commands unless a later prompt requests it. Never delete `rg-eci-dev`.

## Phase 16A verified current state (read-only)

Authenticated inventory on 2026-08-25. No create/update/delete.

```text
rg-eci-deploy-dev
├── ACR                         eciacrdev6c (Basic; eci-api:dd55327 / stable)
├── UAMI                        eci-ca-identity-dev (AcrPull + Foundry User; no Key Vault role)
├── LAW                         eci-law-dev
├── CAE                         eci-ca-env-dev
├── Container App               eci-api-dev
│   ├── image                   eciacrdev6c.azurecr.io/eci-api:dd55327
│   ├── revision                eci-api-dev--0000003 (ScaledToZero)
│   ├── ingress                 external HTTPS, allowInsecure=false, operator /32
│   └── scale                   min 0 / max 1
└── Key Vault                   eci-kv-oauth-dev-susanta (RBAC on)

rg-eci-dev                      Foundry eci-foundry-dev-susanta / eci-project-dev / eci-gpt-54-mini
Azure PostgreSQL                none
Azure Static Web Apps           none
```

Phase 16 hosting freeze: Azure Static Web Apps → this ACA FQDN. See [Phase 16](../../docs/roadmap/phase-16-cloud-browser-multicloud-validation.md) and [ADR-026](../../docs/decisions/ADR-026-cloud-hosted-browser-topology-and-multi-cloud-https-validation.md). Do not create SWA or PostgreSQL from this runbook unless a later phase explicitly authorizes it.

## Current architecture vs this historical runbook (Phase 13/14)

This file remains the Phase 6C/7 Azure hosting procedure. Commands and resource names below are historical. They were not re-executed in Phase 13 or Phase 14.

Current ECI application architecture (code and documentation; not a claim that `eci-api-dev` was redeployed):

- Application-user OIDC exists (`AUTH_MODE=oidc`; live Entra is the first IdP). Analyze is not an anonymous public API.
- Mailbox delegated OAuth is a separate identity domain from that login (Gmail/Microsoft consent → opaque credential store → `ConnectorAccount.credential_ref`).
- Azure Key Vault is the durable mailbox OAuth credential backend (`CREDENTIAL_STORE_BACKEND=azure_key_vault`, `AZURE_KEY_VAULT_URL` only). Runtime identity is `DefaultAzureCredential` / Container Apps managed identity. Phase 13E live-validated the existing development Key Vault `eci-kv-oauth-dev-susanta` at the store/factory path.
- Durable stores require PostgreSQL advisory-lock coordination. PostgreSQL does not store OAuth tokens.
- Production ACA would use managed identity for Key Vault. The retained Container App image (`eci-api:phase7a-5f4f5f8` / later CD tags recorded elsewhere) has **not** been redeployed or certified as a complete Phase 13 mailbox-OAuth runtime or a Phase 14 mailbox→AI runtime. Phase 14 live proof used local ECI runtime + real Entra OIDC + real Gmail/Graph mailboxes + local PostgreSQL + `MockAIProvider`. It did not certify ACA-hosted mailbox→AI and did not call Foundry.

See [Authentication](../../docs/cloud/authentication.md), [Phase 13](../../docs/roadmap/phase-13-mailbox-delegated-oauth.md), [Phase 14](../../docs/roadmap/phase-14-connected-mailbox-analysis.md), and [ADR-023](../../docs/decisions/ADR-023-mailbox-credential-lifecycle-disconnect-and-reauthorization.md).

## Current operational state (Phase 7)

```text
rg-eci-deploy-dev
├── Azure Container Registry     eciacrdev6c
├── User-assigned identity       eci-ca-identity-dev
├── Log Analytics workspace      eci-law-dev   (PerGB2018, 30 days)
└── Container Apps environment   eci-ca-env-dev
    └── logs destination         log-analytics
    └── Container App            eci-api-dev
        └── image                eci-api:phase7a-5f4f5f8
        └── revision             eci-api-dev--0000001
        └── scale                min 0 / max 1
```

Historical inspection: query Log Analytics table `ContainerAppConsoleLogs_CL` (application JSON) and `ContainerAppSystemLogs_CL` (platform events). Native Container Apps metrics to inspect: `Requests`, `ResponseTime`, `Replicas`, `CpuPercentage`, `MemoryPercentage`, `RestartCount`.

Do **not** use `az containerapp logs show` for routine history. Attaching to the live console stream can wake a scale-to-zero replica. Use live streaming only for active diagnostics.

UAMI, secret count 0, ACR admin disabled, and operator `/32` ingress are unchanged. Phase 7B did not call Foundry.

## Purpose

Deploy one provider-independent ECI image:

```text
local verified image
→ Azure Container Registry
→ Azure Container Apps
→ user-assigned Managed Identity
→ Microsoft Foundry
```

Runtime provider:

```text
AI_PROVIDER=microsoft_foundry
```

The same image remains usable later for Amazon Bedrock. This runbook is Azure-only.

## Existing Foundry target (do not modify)

Use the current ECI development Foundry environment. **Do not create, update, or delete anything in `rg-eci-dev`.**

| Item | Value |
|---|---|
| Resource group | `rg-eci-dev` |
| Region | Spain Central (`spaincentral`) |
| Foundry resource | `eci-foundry-dev-susanta` |
| Foundry project | `eci-project-dev` |
| Project endpoint | `https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev` |
| Model deployment | `eci-gpt-54-mini` |

## New deployment resources (this runbook only)

All new resources go in a **separate** resource group so they can be deleted later without touching Foundry:

```text
rg-eci-deploy-dev
├── Azure Container Registry     eciacrdev6c
├── User-assigned identity       eci-ca-identity-dev
├── Log Analytics workspace      eci-law-dev   (added in Phase 7B)
└── Container Apps environment   eci-ca-env-dev
    └── Container App            eci-api-dev
```

**Never** run `az group delete --name rg-eci-dev`.

## Prerequisites confirmed during Prompt 4

- Azure CLI `2.89.1`; `az containerapp` is available without installing the `containerapp` extension.
- Active subscription name: `ECI-Development`.
- Signed-in operator has **Owner** (sufficient to create resources and role assignments).
- Local image `enterprise-communication-intelligence-eci:latest` exists (Prompt 3 verified).
- Built-in role **Foundry User** exists. Role **Azure AI User** does not exist in this subscription.
- These resource providers are **not registered** and must be registered in Prompt 5 **before** creating ACR / Container Apps:
  - `Microsoft.App`
  - `Microsoft.ContainerRegistry`
- Already registered: `Microsoft.ManagedIdentity`, `Microsoft.CognitiveServices`.
- `Microsoft.OperationalInsights` is unregistered. This runbook uses `--logs-destination none`, so it should not be required.

If `az containerapp` is missing when Prompt 5 starts, install it then:

```bash
az extension add --name containerapp
```

Do not add Terraform, Bicep, GitHub Actions, Application Insights, or authentication middleware.

## Identity model

One user-assigned managed identity does both:

1. **AcrPull** — Container Apps pulls the configured image tag from ACR (current: `eci-api:phase7a-5f4f5f8`).
2. **Foundry User** — ECI runtime authenticates with `DefaultAzureCredential()` to Microsoft Foundry.

ECI constructs `DefaultAzureCredential()` with no client ID in application code. Installed `azure-identity` (`1.25.3` in the verified image) reads `AZURE_CLIENT_ID` for user-assigned managed identity selection.

Therefore Prompt 5 **must** set:

```text
AZURE_CLIENT_ID=<user-assigned-identity-client-id>
```

`AZURE_CLIENT_ID` is an identifier, not a secret.

Do **not** set `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, Foundry API keys, or ACR admin passwords.

## Ingress / security

Historical Phase 6C context: at that time the deployed image had no application-user authentication, so `POST /api/v1/communications/analyze` must not stay open to the internet. Phase 8 later added OIDC. Network `/32` restriction remains operator access control and is not a substitute for API authentication.

Plan:

- External HTTPS ingress on target port `8000`.
- Immediately after create, allow only the operator public IP `/32`.
- Leave that restriction in place after verification.

Do not write the operator IP into this repository.

## Health probes

The current Container Apps CLI has **no** first-class HTTP probe flags. HTTP probes would require a YAML artifact.

Phase 6C uses **default TCP probes** on ingress port `8000` (no extra YAML). Operator verification still calls:

- `GET /health`
- `GET /api/v1/readiness`
- `GET /api/v1/health`

## Logging

Phase 6C created the environment with `--logs-destination none`. Phase 7B registered `Microsoft.OperationalInsights`, created workspace `eci-law-dev` (30-day retention), and set the environment destination to `log-analytics`.

Routine historical inspection:

```text
Log Analytics workspace eci-law-dev
→ ContainerAppConsoleLogs_CL
→ filter ContainerAppName_s == "eci-api-dev"
```

Live console streaming (`az containerapp logs show --follow`) can start a scale-to-zero replica. Use it only for active diagnostics, not for routine history. That command is a diagnostic action, not a configuration change.

Do not add Application Insights, OpenTelemetry, dashboards, or alerts.

## Image strategy

Push the **already verified** local image. Do **not** use `az acr build` and do **not** rebuild unless the local image is missing.

```text
enterprise-communication-intelligence-eci:latest
→ ${ACR_NAME}.azurecr.io/eci-api:phase6c
```

---

## Prompt 5 execution

Run from a Bash shell in WSL, at the repository root. Commands are individually executable. The script stops on failure.

Replace nothing with subscription IDs, tenant IDs, or secrets.

### 1. Confirm subscription and local image

```bash
set -euo pipefail

az account show --query name --output tsv
# Expected: ECI-Development
# If not, stop. Do not run az account set unless instructed.

docker image inspect enterprise-communication-intelligence-eci:latest >/dev/null
```

### 2. Define shell variables

```bash
LOCATION="spaincentral"
DEPLOY_RG="rg-eci-deploy-dev"
FOUNDRY_RG="rg-eci-dev"
FOUNDRY_ACCOUNT="eci-foundry-dev-susanta"
FOUNDRY_PROJECT_ENDPOINT="https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
FOUNDRY_MODEL_DEPLOYMENT="eci-gpt-54-mini"

ACR_NAME="eciacrdev6c"
ACR_SKU="Basic"
IMAGE_REPO="eci-api"
IMAGE_TAG="phase6c"
LOCAL_IMAGE="enterprise-communication-intelligence-eci:latest"

IDENTITY_NAME="eci-ca-identity-dev"
CA_ENV_NAME="eci-ca-env-dev"
CA_APP_NAME="eci-api-dev"

OPERATOR_PUBLIC_IP="$(curl -sS https://api.ipify.org)"
echo "Operator public IP will be used as ${OPERATOR_PUBLIC_IP}/32"
# Do not commit this value.
```

If `az acr check-name --name "${ACR_NAME}"` reports the name is taken when Prompt 5 starts, choose another `eciacrdev<suffix>` and re-check before creating the registry.

### 3. Register required resource providers

```bash
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.ContainerRegistry --wait

az provider show --namespace Microsoft.App --query registrationState --output tsv
az provider show --namespace Microsoft.ContainerRegistry --query registrationState --output tsv
# Expected: Registered
```

Do not register `Microsoft.OperationalInsights` unless a later step is changed to Log Analytics.

### 4. Create the deployment resource group

```bash
az group create \
  --name "${DEPLOY_RG}" \
  --location "${LOCATION}"
```

### 5. Create ACR (Basic, admin disabled)

```bash
az acr create \
  --name "${ACR_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --location "${LOCATION}" \
  --sku "${ACR_SKU}" \
  --admin-enabled false \
  --role-assignment-mode rbac

# Azure reports this mode as roleAssignmentMode=LegacyRegistryPermissions.
# That is standard Azure RBAC (AcrPull/AcrPush), not ABAC.

ACR_ID="$(az acr show --name "${ACR_NAME}" --resource-group "${DEPLOY_RG}" --query id --output tsv)"
ACR_LOGIN_SERVER="$(az acr show --name "${ACR_NAME}" --resource-group "${DEPLOY_RG}" --query loginServer --output tsv)"
echo "ACR login server: ${ACR_LOGIN_SERVER}"
```

Prompt 5 observed `authentication-as-arm` already `enabled` after ACR create. Confirm:

```bash
az acr config authentication-as-arm show --registry "${ACR_NAME}"
```

Enable it only if the status is disabled.

### 6. Create the user-assigned managed identity

```bash
az identity create \
  --name "${IDENTITY_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --location "${LOCATION}"

IDENTITY_ID="$(az identity show --name "${IDENTITY_NAME}" --resource-group "${DEPLOY_RG}" --query id --output tsv)"
IDENTITY_CLIENT_ID="$(az identity show --name "${IDENTITY_NAME}" --resource-group "${DEPLOY_RG}" --query clientId --output tsv)"
IDENTITY_PRINCIPAL_ID="$(az identity show --name "${IDENTITY_NAME}" --resource-group "${DEPLOY_RG}" --query principalId --output tsv)"
```

Do not paste these IDs into git-tracked files.

### 7. Assign AcrPull on the registry

```bash
az role assignment create \
  --assignee-object-id "${IDENTITY_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "${ACR_ID}"
```

### 8. Assign Foundry User on the existing Foundry account

Verified role name: **Foundry User**.

Scope: Foundry account `eci-foundry-dev-susanta` in `rg-eci-dev` (covers project `eci-project-dev` data-plane inference).

```bash
FOUNDRY_ACCOUNT_ID="$(az cognitiveservices account show \
  --name "${FOUNDRY_ACCOUNT}" \
  --resource-group "${FOUNDRY_RG}" \
  --query id \
  --output tsv)"

az role assignment create \
  --assignee-object-id "${IDENTITY_PRINCIPAL_ID}" \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "${FOUNDRY_ACCOUNT_ID}"
```

Wait briefly for RBAC propagation before the first Foundry call (often 1–3 minutes).

### 8b. Assign operator AcrPush on the new registry

Do not assign AcrPush to the Container Apps identity.

```bash
OPERATOR_OBJECT_ID="$(az ad signed-in-user show --query id --output tsv)"

az role assignment create \
  --assignee-object-id "${OPERATOR_OBJECT_ID}" \
  --assignee-principal-type User \
  --role AcrPush \
  --scope "${ACR_ID}"
```

### 9. Login, tag, and push the verified local image

```bash
az acr login --name "${ACR_NAME}"

docker tag "${LOCAL_IMAGE}" "${ACR_LOGIN_SERVER}/${IMAGE_REPO}:${IMAGE_TAG}"
docker push "${ACR_LOGIN_SERVER}/${IMAGE_REPO}:${IMAGE_TAG}"
```

### 10. Create the Container Apps environment

Consumption-style environment: no dedicated workload profiles, no VNet, no Log Analytics workspace.

```bash
az containerapp env create \
  --name "${CA_ENV_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --location "${LOCATION}" \
  --enable-workload-profiles false \
  --logs-destination none
```

If Spain Central rejects `--enable-workload-profiles false`, recreate **without** that flag (CLI default enables workload profiles, which still includes a Consumption profile). Do not add Dedicated profiles, zone redundancy, or a VNet.

### 11. Create the Container App

Uses the user-assigned identity for both registry pull and runtime. Ingress is created external, then restricted in the next step.

```bash
az containerapp create \
  --name "${CA_APP_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --environment "${CA_ENV_NAME}" \
  --image "${ACR_LOGIN_SERVER}/${IMAGE_REPO}:${IMAGE_TAG}" \
  --registry-server "${ACR_LOGIN_SERVER}" \
  --registry-identity "${IDENTITY_ID}" \
  --user-assigned "${IDENTITY_ID}" \
  --target-port 8000 \
  --ingress external \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 0 \
  --max-replicas 1 \
  --env-vars \
    AI_PROVIDER=microsoft_foundry \
    APP_ENV=production \
    FOUNDRY_PROJECT_ENDPOINT="${FOUNDRY_PROJECT_ENDPOINT}" \
    FOUNDRY_MODEL_DEPLOYMENT="${FOUNDRY_MODEL_DEPLOYMENT}" \
    AZURE_CLIENT_ID="${IDENTITY_CLIENT_ID}"
```

Do not pass AWS keys, Azure client secrets, or ACR passwords.

### 12. Restrict ingress to the operator IP immediately

```bash
az containerapp ingress access-restriction set \
  --name "${CA_APP_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --rule-name phase6c-operator \
  --ip-address "${OPERATOR_PUBLIC_IP}/32" \
  --action Allow \
  --description "Phase 6C operator verification"
```

After an Allow rule exists, other public IPs are denied. Leave this restriction in place.

### 13. Verify revision / FQDN

```bash
az containerapp show \
  --name "${CA_APP_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --query "{fqdn:properties.configuration.ingress.fqdn,running:properties.runningStatus,latest:properties.latestRevisionName}" \
  --output json

APP_FQDN="$(az containerapp show \
  --name "${CA_APP_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)"

echo "https://${APP_FQDN}"
```

If the revision is stuck pulling, confirm AcrPull and `--registry-identity`. If the app starts but analyze returns 401/403, wait for Foundry User propagation and confirm `AZURE_CLIENT_ID`.

### 14. Call health and readiness

```bash
curl -sS -i "https://${APP_FQDN}/health"
curl -sS -i "https://${APP_FQDN}/api/v1/readiness"
curl -sS -i "https://${APP_FQDN}/api/v1/health"
```

Expect HTTP 200. Versioned health should show `"environment":"production"`.

### 15. Call analyze (Foundry)

This step performs **paid** Microsoft Foundry inference. Run it once for verification.

```bash
curl -sS -X POST "https://${APP_FQDN}/api/v1/communications/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "Please review the project update and confirm whether any follow-up is required.",
      "message_id": "azure-containerapps-live-001",
      "metadata": {
        "source_type": "email",
        "sender": "manager@example.com",
        "recipients": ["user@example.com"],
        "subject": "Project update"
      }
    },
    "include_draft_reply": true,
    "include_action_items": true
  }'
```

Expect HTTP 200 and `"provider": "microsoft_foundry"`.

### 16. Inspect platform logs only if needed

```bash
az containerapp logs show \
  --name "${CA_APP_NAME}" \
  --resource-group "${DEPLOY_RG}" \
  --tail 50
```

Do not add monitoring products.

### 17. Leave the app restricted

Do not remove the IP allow rule. Do not enable unrestricted public ingress.

Scale-to-zero (`min-replicas 0`) is already configured. Idle Container Apps Consumption cost should stay low; **ACR Basic still incurs a standing registry charge** until `rg-eci-deploy-dev` is deleted.

---

## Cleanup (not part of the deployment path)

Before deleting, confirm the group contains only Phase 6C deployment resources:

```bash
az resource list --resource-group rg-eci-deploy-dev --output table
```

Expected kinds of resources: ACR, user-assigned identity, Log Analytics workspace, Container Apps environment, Container App. **Foundry must not appear here.**

Then, only when cleanup is explicitly requested:

```bash
az group delete \
  --name rg-eci-deploy-dev \
  --yes \
  --no-wait
```

**Never:**

```bash
az group delete --name rg-eci-dev
```

---

## Out of scope

- Terraform / Bicep / ARM templates / GitHub Actions
- AKS, VNet, private endpoints, API Gateway
- Application Insights, dashboards, alerts
- Application-user authentication
- Changing `Dockerfile`, application code, or Foundry resources
