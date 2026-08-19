# ADR-011: Secretless GitHub Actions Multi-Cloud CI/CD

## Status

Accepted

The decision is implemented. Phase 8C added CI and manual CD workflows with GitHub OIDC federation. Phase 8D executed `deploy.yml` with `target=both` and verified Azure and AWS token exchange. No long-lived Azure client secrets or AWS access keys are stored in GitHub.

## Date

Phase 8 (Production Hardening)

## Context

ECI needed automatic quality gates and an explicit multi-cloud deploy path without long-lived Azure client secrets or AWS access keys. Runtime workload identities must not be reused for deployment. Application-user OIDC is a third identity class.

## Decision

Keep CI automatic and CD manual.

```text
CI (pull_request, push to master)
→ Python 3.12
→ pip check, ruff, pytest
→ contents: read only
→ no Docker, no cloud, no id-token
```

```text
CD (workflow_dispatch only, target azure | aws | both)
→ one GitHub-hosted Docker build
→ SHA tag (first 7 of GITHUB_SHA) and stable
→ GitHub Environment azure → OIDC → eci-github-deploy-dev UAMI → ACR / Container Apps
→ GitHub Environment aws → OIDC → eci-github-deploy-dev IAM role → ECR / ECS
```

GitHub OIDC subjects use immutable unique IDs:

```text
repo:Susanta2025-lab@238117232/enterprise-communication-intelligence@1320232309:environment:azure
repo:Susanta2025-lab@238117232/enterprise-communication-intelligence@1320232309:environment:aws
```

Deploy identities are not runtime identities:

- Azure UAMI `eci-github-deploy-dev` is not `eci-ca-identity-dev` and has no Foundry User role.
- AWS IAM role `eci-github-deploy-dev` is not `eci-developer`, `eci-bedrock-task-role-dev`, or `eci-ecs-execution-role-dev`.

AWS CD describes the live task definition, strips RegisterTaskDefinition response-only fields, and changes only the application container image. Desired count, networking, and Bedrock environment are not redesigned by the workflow.

Infrastructure remains manually provisioned. The workflow deploys an image; it does not create clouds.

## Alternatives Considered

- **Push/tag automatic deployment** — rejected. Production fail-closed auth makes accidental image rollout unsafe.
- **Independent Azure and AWS rebuilds** — rejected. `target=both` must deliver the same image content.
- **Long-lived cloud keys in GitHub secrets** — rejected. OIDC federation is sufficient.
- **Reusing runtime UAMI / task role / eci-developer** — rejected. Identity classes must stay separate.

## Consequences

- First verified multi-cloud deployment used commit `dd55327` and identical registry digest `sha256:0590bf6f7b2ae5614dd35af0307763cb0303e98948531bab2352258e6773ed70` in ACR and ECR.
- Azure revision uses image `eci-api:dd55327`. AWS task definition is `eci-api-dev:4`.
- `eci-developer` still cannot inspect AWS IAM OIDC objects; those were created by an administrator. Inspection remains denied; creation is complete.
- Phase 8B ELBv2 verification policy is not used for CD. Cleanup of `ECIPhase8BIngressVerificationPolicy`, if still attached, remains an IAM-admin follow-up.

## Benefits

- no long-lived deploy secrets
- one build reused across clouds
- least-privilege deploy identities
- explicit operator trigger

## Trade-offs

- CD cannot run until workflows are on the default branch
- AWS IAM policy body remains operator-attested to `eci-developer`
- CD does not provision identity providers, domains, or load balancers

## Deferred Work

- automatic (push/tag) cloud deployment
- infrastructure provisioning from GitHub Actions
- Key Vault / Secrets Manager as part of CD

## Related Components

- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml`
- [Deployment](../cloud/deployment.md)
- ADR-009 (Application-User Authentication)
- ADR-010 (Multi-Cloud Production Ingress)
