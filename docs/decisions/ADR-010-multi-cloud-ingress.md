# ADR-010: Multi-Cloud Production Ingress Strategy

## Status

Accepted

The decision is implemented as a split live/deferred model. Azure uses platform-managed HTTPS. AWS ALB architecture was verified in Phase 8B and torn down for cost control. AWS production TLS remains domain/ACM gated.

## Date

Phase 8 (Production Hardening)

## Context

ECI needed production-shaped ingress without standing multi-cloud load-balancer cost. Azure Container Apps already terminates TLS on the default FQDN. AWS Fargate had only an operator `/32` HTTP task path. A persistent ALB without a custom domain cannot provide the HTTPS identity required to send real bearer tokens.

Application-user JWTs (ADR-009) must not travel over plaintext HTTP.

## Decision

Use Azure Container Apps external HTTPS as the live Azure ingress. Set `allowInsecure=false`. Keep operator `/32` restriction. Do not add Front Door, Application Gateway, or WAF in this phase.

```text
Azure (live)
HTTPS → Azure Container Apps → ECI
```

On AWS, verify the production architecture once:

```text
HTTPS / domain / ACM → ALB → target group → Fargate :8000
```

Then delete the ALB, listener, target group, and temporary security group. Retain operator `/32` on TCP 8000. Treat direct task HTTP as verification-only. Never send a real application-user bearer token over that HTTP path.

A custom domain and ACM certificate are required before AWS HTTPS is restored.

```text
AWS (current, verification-only)
operator /32 HTTP → ECS task → ECI

AWS (verified, not retained)
HTTPS domain + ACM → ALB → ECS Fargate → ECI
```

## Alternatives Considered

- **Persistent AWS ALB on HTTP** — rejected. It would add standing cost without TLS and would still be unsafe for bearer tokens.
- **Public `0.0.0.0/0` on 8000** — rejected. Operator restriction remains required.
- **Azure extra load balancer (Front Door, Application Gateway, WAF)** — rejected. Container Apps already provides HTTPS and a stable FQDN.

## Consequences

- Azure authenticated traffic uses managed TLS (`allowInsecure=false`, operator `/32`).
- AWS real-token / Bedrock authorized verification waits for a domain and ACM certificate.
- Idle cost stays low: Azure min replicas 0, AWS desiredCount 0, no standing ALB.

## Benefits

- live Azure HTTPS without extra Azure load-balancing products
- proven AWS ALB architecture without retaining its cost
- explicit security rule for plaintext HTTP

## Trade-offs

- AWS has no persistent HTTPS hostname
- AWS authorized inference is not end-to-end TLS-verified
- restoring AWS HTTPS requires domain registration and ACM before an ALB is recreated

## Deferred Work

- AWS custom domain and ACM certificate
- recreating HTTPS domain → ALB → Fargate after that domain exists
- Azure Front Door, Application Gateway, WAF, and custom domains

## Related Components

- [Deployment](../cloud/deployment.md)
- [Authentication](../cloud/authentication.md)
- ADR-009 (Application-User Authentication)
- Phase 8B ingress verification
