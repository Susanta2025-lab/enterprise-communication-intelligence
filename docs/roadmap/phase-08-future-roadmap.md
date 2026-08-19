# Phase 08 — Production Hardening

## Objective

Harden ECI for production operation: application-user authentication, production ingress, GitHub Actions CI/CD with cloud OIDC, and cross-cloud verification.

## Business Value

Separate application-user identity, runtime workload identity, and deployment identity. Keep CI automatic and CD explicit. Avoid long-lived cloud credentials.

## Deliverables

- [x] Phase 8A — application JWT/OIDC authentication (fail-closed in production)
- [x] Phase 8B — Azure managed HTTPS ingress confirmed; AWS ALB architecture verified then torn down
- [x] Phase 8C — GitHub Actions CI/CD and cloud OIDC federation
- [ ] Phase 8D — cross-cloud verification and documentation consolidation

## Tasks

- [x] Protect analyze; keep health public; disable production OpenAPI docs
- [x] Verify Azure Container Apps HTTPS; add no extra Azure load balancer
- [x] Temporarily prove AWS ALB → target group → Fargate; delete ALB afterward
- [x] Add CI workflow (Python 3.12, pip check, ruff, pytest)
- [x] Add manual CD workflow (azure | aws | both, build-once, SHA + stable tags)
- [x] Create Azure GitHub deploy identity `eci-github-deploy-dev` with federated credential for environment `azure`
- [x] IAM administrator: create AWS GitHub OIDC provider and role `eci-github-deploy-dev` (`eci-developer` cannot inspect IAM)
- [x] Configure GitHub Environments `azure` and `aws` plus non-secret identifier variables
- [ ] Provision live application-user OIDC issuer/audience/JWKS
- [ ] Execute CD in Phase 8D after OIDC configuration exists

## Architectural Decisions

- CI never deploys and never requests `id-token`.
- CD is `workflow_dispatch` only.
- Azure deploy UAMI is not the Container Apps runtime identity and has no Foundry User role.
- AWS deploy role must not be `eci-developer`, the Bedrock task role, or the ECS execution role.
- GitHub OIDC trust is repository- and environment-scoped using immutable unique-ID subjects.
- Do not deploy commit `cd8a08d` until live application-user OIDC settings exist.

## Acceptance Criteria

- [x] CI tests-only workflow exists
- [x] Manual CD workflow exists with build-once SHA/stable tagging
- [x] Azure GitHub OIDC deploy identity created with least-privilege RBAC
- [x] AWS GitHub OIDC provider and deploy role created
- [x] GitHub Environments configured
- [x] No application image deployed during Phase 8C
- [x] No long-lived Azure/AWS credentials in the repository

## Risks and Trade-offs

`eci-developer` cannot inspect AWS IAM OIDC/role objects; those were created by an IAM administrator. ACR ARM read required a resource-scoped Reader assignment in addition to AcrPush. AWS HTTPS remains domain-gated. Persistent ALB is intentionally absent for cost control.

## Lessons Learned

Phase 8B ELBv2 and Phase 8C IAM OIDC both required administrator policy grants that the local operator identity does not hold.

## Next Phase

Phase 8D — provision application-user OIDC, execute CD against both clouds, and consolidate documentation.
