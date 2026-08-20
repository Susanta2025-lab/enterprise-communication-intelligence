# Endpoints

All HTTP endpoints implemented in the repository as of Phase 10. Phase 10 added **no** connector HTTP endpoints. There is no `/api/v1/connectors` route. Connector capability currently exists below the HTTP product surface (`CommunicationConnector` → `CommunicationIngestionService` → existing analysis workflow).

## `GET /health`

**Purpose:** Lightweight, platform-level liveness signal. Intended for infrastructure health checks that should not depend on application configuration.

- **Method:** `GET`
- **Path:** `/health` (unversioned; defined in `app/api/routes/health.py` as `liveness_router`, mounted directly on the app in `app/main.py`)
- **Request body:** none
- **Response model:** `LivenessResponse` (`app/schemas/health.py`)
- **Response body:**
  ```json
  { "status": "healthy" }
  ```
- **Status codes:** `200 OK`
- **Authentication:** none. This endpoint does not validate tokens and does not call OIDC, Foundry, or Bedrock.
- **Headers:** `X-Request-ID` is always set by the server. An incoming value is ignored.

**Limitations:** Always returns `healthy`; it does not check downstream dependencies, including PostgreSQL.

---

## `GET /api/v1/health`

**Purpose:** Versioned application health metadata, including service identity and environment.

- **Method:** `GET`
- **Path:** `{API_V1_PREFIX}/health` → `/api/v1/health` by default
- **Request body:** none
- **Response model:** `HealthResponse` (`app/schemas/health.py`)
- **Response body:**
  ```json
  {
    "status": "healthy",
    "service": "Enterprise Communication Intelligence Platform",
    "version": "0.1.0",
    "environment": "development"
  }
  ```
  `service`, `version`, and `environment` are read from `Settings` (`app_name`, `app_version`, `app_env`).
- **Status codes:** `200 OK`
- **Authentication:** none.

**Limitations:** Reflects configuration values only; does not probe any external system.

---

## `GET /api/v1/readiness`

**Purpose:** Confirm that application configuration loaded successfully and, when persistence is configured, that the database responds to `SELECT 1`.

- **Method:** `GET`
- **Path:** `{API_V1_PREFIX}/readiness` → `/api/v1/readiness` by default
- **Request body:** none
- **Response model:** `ReadinessResponse` (`app/schemas/health.py`)
- **Response body:**
  ```json
  { "status": "ready" }
  ```
- **Status codes:**
  - `200 OK` — configuration loaded; if `DATABASE_URL` is set, the database probe succeeded
  - `503 Service Unavailable` — persistence is configured and the database is unavailable. Body: `{"detail": "Persistence is currently unavailable."}`
- **Authentication:** none. Does not call Azure, AWS, or OIDC.

**Behavior:**

- Persistence disabled: ready
- Persistence configured and the database is healthy: ready
- Persistence configured and the database is unavailable: `503`

**Limitations:** Does not probe Microsoft Foundry, Amazon Bedrock, or OIDC JWKS. Process liveness remains `GET /health`. No database host or driver detail is returned.

---

## `POST /api/v1/communications/analyze`

**Purpose:** Analyze a single business communication and return a structured analysis (summary, priority, category, action items, and optionally a draft reply), produced by the configured `AIProvider`.

- **Method:** `POST`
- **Path:** `{API_V1_PREFIX}/communications/analyze` → `/api/v1/communications/analyze` by default
- **Request requirements:**
  - `Content-Type: application/json`
  - Body must conform to `CommunicationRequest` (see [Request/Response Models](request-response-models.md))
  - `message.body` must be non-empty (after trimming whitespace)
  - `message.metadata.source_type` must be a valid `SourceType` enum value
  - `message.metadata.sender` must be non-empty
  - Unknown top-level or nested fields are rejected (all domain models use `extra="forbid"`)
- **Authentication:** required when `AUTH_MODE=oidc`. Send `Authorization: Bearer <JWT>`. The token must pass signature, issuer, audience, and expiry checks and include permission `communications:analyze` in `scp`, `scope`, or `roles`. When `AUTH_MODE=disabled` (development default), no token is required.
- **Response model:** `CommunicationAnalysisResponse` (see [Request/Response Models](request-response-models.md))
- **Status codes:**
  - `200 OK` — analysis completed successfully. `analysis_id` is included only when persistence stored the result.
  - `401 Unauthorized` — missing, malformed, expired, or otherwise invalid bearer token
  - `403 Forbidden` — authenticated token lacks `communications:analyze`
  - `422 Unprocessable Entity` — request failed Pydantic/FastAPI validation
  - `500 Internal Server Error` — the AI provider failed, or the configured `AI_PROVIDER` is unsupported (see [Error Handling](error-handling.md))
  - `503 Service Unavailable` — persistence is configured and identity/database resolution failed before the AI call. Body: `{"detail": "Persistence is currently unavailable."}`

**Persistence behavior:**

- Persistence disabled or unauthenticated development: `200`, `analysis_id` omitted
- Authenticated + persistence configured + save succeeds: `200`, `analysis_id` returned
- Authenticated + identity/DB failure before AI: `503`, AI call count = 0
- AI succeeds + save fails: `200` with the analysis, `analysis_id` omitted, AI call count = 1, no retry

**Limitations:**
- History storage does not include the raw communication body.
- Rate limiting is not implemented.
- Synchronous request/response only — no streaming or WebSocket support.

---

## `GET /api/v1/analyses`

**Purpose:** Return a bounded page of analyses owned by the authenticated caller.

- **Method:** `GET`
- **Path:** `{API_V1_PREFIX}/analyses` → `/api/v1/analyses` by default
- **Query parameters:** `limit` (1–100, default 20), `offset` (>= 0, default 0)
- **Authentication:** always required. History uses `require_authenticated_communications_analyze`: `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, send `Authorization: Bearer <JWT>` with permission `communications:analyze`.
- **Response model:** `AnalysisHistoryListResponse`
- **Status codes:**
  - `200 OK` — page of owned items; callers without an identity mapping receive an empty page
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

History items include structured analysis fields. They do not include raw communication content or identity claims.

---

## `GET /api/v1/analyses/{analysis_id}`

**Purpose:** Return one analysis owned by the authenticated caller.

- **Method:** `GET`
- **Path:** `/api/v1/analyses/{analysis_id}`
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:analyze`.
- **Response model:** `AnalysisHistoryItem`
- **Status codes:**
  - `200 OK` — owned analysis
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `404 Not Found` — unknown id or owned by a different user. Body: `{"detail": "Analysis not found."}`
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

Cross-user access is indistinguishable from an unknown id.

---

## `DELETE /api/v1/analyses/{analysis_id}`

**Purpose:** Hard-delete an analysis owned by the authenticated caller.

- **Method:** `DELETE`
- **Path:** `/api/v1/analyses/{analysis_id}`
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:analyze`.
- **Status codes:**
  - `204 No Content` — deleted
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `404 Not Found` — unknown id or owned by a different user
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted
