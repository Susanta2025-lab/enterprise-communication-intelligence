# ADR-008: Portable Structured Observability

## Status

Accepted

The decision is implemented. Phase 7A application telemetry is in the codebase. Phase 7B Azure Log Analytics and native Container Apps metrics are live-verified. Phase 7C CloudWatch Logs and standard ECS/Fargate metrics are live-verified.

## Date

Phase 7 (Observability)

## Context

ECI needed operational visibility after the Phase 6C multi-cloud deployment without adding a second observability stack per cloud. The application is a small single-service portfolio platform. Logs must stay privacy-safe. Azure Container Apps can scale to zero. The AWS service is idle at `desiredCount=0`.

Distributed tracing, custom metrics, dashboards, and alerts would add collectors, cost, and operational surface that the current architecture does not require.

## Decision

Use portable structured application logs with request correlation and duration fields, combined with native cloud log retention and platform metrics. Defer distributed tracing and custom metric infrastructure until application complexity justifies it.

```text
ECI
→ request_id
→ structured operational events
→ duration_ms
→ privacy-safe stdout JSON

Azure: same image → Container Apps → Log Analytics + Azure Monitor platform metrics
AWS: same image → ECS Fargate → CloudWatch Logs + standard AWS/ECS metrics
```

No provider-specific application observability SDK is required beyond structlog.

## Alternatives Considered

- **OpenTelemetry** — deferred. A vendor-neutral collector would add an SDK, export pipeline, and operational ownership before ECI has multiple services or tracing requirements.
- **Application Insights** — deferred. Azure-specific APM would couple application telemetry to one cloud and add a second billing surface.
- **Container Insights / enhanced Container Insights** — deferred. Standard AWS/ECS CPU and memory metrics were sufficient for Phase 7C.
- **ADOT sidecar / AWS X-Ray** — deferred. Tracing and extra sidecars are not justified for one Fargate service that is usually scaled to zero.
- **Prometheus / Grafana** — deferred. No scrape targets, dashboards, or SRE workflow exist yet.

## Consequences

- Application logs remain JSON on stdout and work on both clouds without code changes.
- `request_id` / `X-Request-ID` is the correlation key. Incoming request-id headers are ignored.
- Operational logs use `error_class` and `duration_ms`. They do not emit communication content or `str(exc)`.
- Azure historical inspection uses Log Analytics. Live Container Apps console streaming can wake a scale-to-zero replica and is for active diagnostics only.
- AWS inspection uses CloudWatch Logs and standard `CPUUtilization` / `MemoryUtilization`. Operator metric-read permissions belong to `eci-developer`, not the task roles.
- Adding tracing or custom metrics later can sit beside this design; it does not require replacing structlog.

## Benefits

- one application telemetry contract for Azure and AWS
- request correlation without a tracing backend
- privacy-safe operational logs
- native platform metrics without extra collectors
- idle cost control (Azure min replicas 0, AWS desiredCount 0)

## Trade-offs

- no distributed traces
- no custom application metrics
- no dashboards, alerts, or SLOs
- AWS has no native request-count/response-time metrics without an ALB
- operators must query each cloud's native log store

## Related Components

- `app/api/middleware.py`
- `app/core/telemetry.py`
- `app/core/logging.py`
- [Observability](../cloud/observability.md)
- [Deployment](../cloud/deployment.md)
- ADR-001 (Clean Architecture Layering)
- ADR-002 (Provider Abstraction for AI Analysis)
