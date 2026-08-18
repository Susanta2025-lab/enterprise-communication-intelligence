# Phase 07 Observability

## Objective

Add portable application telemetry and retain it with native Azure and AWS platform logging and metrics, without introducing tracing, custom metrics, or a second observability stack.

## Business Value

- Operators can correlate a request across API, service, and provider logs with `request_id` / `X-Request-ID`.
- Latency is visible as `duration_ms` without a metrics SDK.
- Communication content stays out of operational logs.
- The same image emits the same JSON on Azure Container Apps and ECS Fargate.
- Idle cost stays controlled: Azure min replicas 0, AWS desiredCount 0.

## Status

Phase 7 is complete:

- **7A is implemented:** structured stdout telemetry, request correlation, `duration_ms`, `error_class`, privacy sentinels. Offline regression: 243 tests passed.
- **7B is live-verified:** Log Analytics workspace `eci-law-dev` (30 days), Container Apps destination `log-analytics`, native Container Apps metrics, image `eci-api:phase7a-5f4f5f8`, revision `eci-api-dev--0000001`, final ScaledToZero.
- **7C is live-verified:** ECR tag `phase7a-5f4f5f8`, task definition `eci-api-dev:2`, CloudWatch Logs `/ecs/eci-api-dev` (1 day), standard AWS/ECS CPU and memory metrics, service returned to desiredCount 0.
- **7D is documentation and final regression.**

## Deliverables

- Application telemetry helpers and HTTP middleware (`app/core/telemetry.py`, `app/api/middleware.py`)
- Privacy-safe structured events on HTTP, service, and provider paths
- Azure Log Analytics attachment and native metric verification
- AWS CloudWatch Logs and standard ECS metric verification
- ADR-008 and observability architecture documentation

## Tasks

- [x] Define vendor-neutral application telemetry
- [x] Bind server-generated `request_id` and return `X-Request-ID`
- [x] Emit `duration_ms` and `error_class` without logging communication content
- [x] Attach Azure Container Apps to Log Analytics (`eci-law-dev`, 30 days)
- [x] Verify retained Azure console logs and native metrics
- [x] Push the Phase 7A image to ECR and register `eci-api-dev:2`
- [x] Verify CloudWatch Logs and standard ECS CPU/memory metrics
- [x] Return AWS desiredCount to 0
- [x] Document architecture, diagrams, runbooks, and roadmap

## Architectural Decisions

- Portable structured logs plus native platform retention/metrics. See [ADR-008](../decisions/ADR-008-observability.md).
- No Application Insights, OpenTelemetry, Container Insights, ADOT, X-Ray, custom metrics, dashboards, or alerts in Phase 7.
- Operator CloudWatch metric-read permissions belong to `eci-developer`, not the ECS task roles.

## Acceptance Criteria

- [x] `request_id` / `X-Request-ID` documented and verified
- [x] `message_id` remains distinct from `request_id`
- [x] Azure Log Analytics retains matching HTTP started/completed events
- [x] Azure native metrics queried
- [x] AWS CloudWatch Logs retain matching HTTP started/completed events
- [x] AWS standard CPU/memory metrics queried
- [x] No Foundry or Bedrock inference used for observability verification
- [x] Azure final replica count 0; AWS desiredCount 0
- [x] Documentation and final regression complete

## Risks and Trade-offs

- Live Azure console streaming can wake a scale-to-zero replica. Prefer Log Analytics for history.
- AWS has no native request-count or response-time metrics without an ALB.
- CloudWatch Logs filter patterns treat hyphens as operators; quote `request_id` when searching.

## Lessons Learned

Native platform logs and metrics were enough to prove Phase 7A telemetry on both clouds. Extra collectors would have added cost without changing the verification outcome.

## Next Phase

Phase 8 – Future Roadmap.

See [Observability](../cloud/observability.md).
