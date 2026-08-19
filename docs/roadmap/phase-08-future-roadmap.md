# Phase 08 — Production Hardening

## Objective

Harden ECI for production operation: application-user authentication, production ingress, GitHub Actions CI/CD with cloud OIDC, and cross-cloud verification.

## Business Value

Separate application-user identity, runtime workload identity, and deployment identity. Keep CI automatic and CD explicit. Avoid long-lived cloud credentials.

## Status

Phase 8 is complete:

- **8A is implemented:** provider-independent OIDC JWT validation, permission `communications:analyze`, fail-closed production startup.
- **8B is live-verified:** Azure Container Apps HTTPS (`allowInsecure=false`, operator `/32`); AWS ALB architecture verified then torn down.
- **8C is implemented:** GitHub Actions CI (tests only) and manual CD with GitHub OIDC federation.
- **8D is live-verified:** Entra single-tenant API resource; CD for commit `dd55327` (`target=both`); Azure real bearer; AWS missing-token and JWKS fail-closed. AWS TLS is an intentional deferred enhancement.

## Deliverables

- [x] Phase 8A — application JWT/OIDC authentication (fail-closed in production)
- [x] Phase 8B — Azure managed HTTPS ingress confirmed; AWS ALB architecture verified then torn down
- [x] Phase 8C — GitHub Actions CI/CD and cloud OIDC federation
- [x] Phase 8D — cross-cloud verification and documentation consolidation

## Tasks

- [x] Protect analyze; keep health public; disable production OpenAPI docs
- [x] Verify Azure Container Apps HTTPS; add no extra Azure load balancer
- [x] Temporarily prove AWS ALB → target group → Fargate; delete ALB afterward
- [x] Add CI workflow (Python 3.12, pip check, ruff, pytest)
- [x] Add manual CD workflow (azure | aws | both, build-once, SHA + stable tags)
- [x] Create Azure GitHub deploy identity `eci-github-deploy-dev` with federated credential for environment `azure`
- [x] IAM administrator: create AWS GitHub OIDC provider and role `eci-github-deploy-dev` (`eci-developer` cannot inspect IAM)
- [x] Configure GitHub Environments `azure` and `aws` plus non-secret identifier variables
- [x] Provision live application-user OIDC issuer/audience/JWKS
- [x] Execute CD in Phase 8D after OIDC configuration exists

## Architectural Decisions

- CI never deploys and never requests `id-token`.
- CD is `workflow_dispatch` only.
- Azure deploy UAMI is not the Container Apps runtime identity and has no Foundry User role.
- AWS deploy role must not be `eci-developer`, the Bedrock task role, or the ECS execution role.
- GitHub OIDC trust is repository- and environment-scoped using immutable unique-ID subjects.
- Never send a real application-user bearer token over AWS HTTP.

See [ADR-009](../decisions/ADR-009-application-user-authentication.md), [ADR-010](../decisions/ADR-010-multi-cloud-ingress.md), and [ADR-011](../decisions/ADR-011-github-actions-oidc-cicd.md).

## Acceptance Criteria

- [x] CI tests-only workflow exists
- [x] Manual CD workflow exists with build-once SHA/stable tagging
- [x] Azure GitHub OIDC deploy identity created with least-privilege RBAC
- [x] AWS GitHub OIDC provider and deploy role created
- [x] GitHub Environments configured
- [x] No long-lived Azure/AWS credentials in the repository
- [x] Live Entra single-tenant API resource configured (`eci-api-auth-dev`, scope `communications:analyze`)
- [x] Production clouds run `AUTH_MODE=oidc`
- [x] CD executed for commit `dd55327` with `target=both`
- [x] ACR and ECR digest equality verified
- [x] Azure real-bearer authorized request verified over HTTPS
- [x] AWS missing-token 401 and JWKS fail-closed verified without a real bearer
- [x] Documentation consolidated (ADRs, diagrams, cloud, architecture, API, README)

## Phase 8D results

- First verified multi-cloud image: commit `dd55327`, tags `dd55327` and `stable`.
- Identical registry digest `sha256:0590bf6f7b2ae5614dd35af0307763cb0303e98948531bab2352258e6773ed70` in ACR and ECR.
- Azure image `eci-api:dd55327`. AWS task definition `eci-api-dev:4`.
- GitHub OIDC token exchange verified on both clouds.
- Azure Foundry inference after auth verified once.
- AWS real-bearer authorized inference deferred until domain/ACM TLS.

## Risks and Trade-offs

`eci-developer` cannot inspect AWS IAM OIDC/role objects; those were created by an IAM administrator. ACR ARM read required a resource-scoped Reader assignment in addition to AcrPush. AWS HTTPS remains domain-gated. Persistent ALB is intentionally absent for cost control. AWS TLS is an intentional deferred enhancement, not a Phase 8 gap in the documented plan. Cleanup of temporary `ECIPhase8BIngressVerificationPolicy`, if still attached, remains an IAM-admin follow-up.

## Lessons Learned

Phase 8B ELBv2 and Phase 8C IAM OIDC both required administrator policy grants that the local operator identity does not hold. Build-once CD produced identical Azure and AWS image digests.

## Next Phase

Phase 9 — Persistence & Multi-Tenant/User-Associated Data.

Do not implement Phase 9 in this phase.

See [Authentication](../cloud/authentication.md) and [Deployment](../cloud/deployment.md).
