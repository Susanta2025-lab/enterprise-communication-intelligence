# Endpoints

All endpoints implemented in the repository as of Phase 5. No other routes exist.

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

**Limitations:** Always returns `healthy`; it does not check downstream dependencies (there are none in this phase).

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

**Purpose:** Confirm that application configuration loaded successfully.

- **Method:** `GET`
- **Path:** `{API_V1_PREFIX}/readiness` → `/api/v1/readiness` by default
- **Request body:** none
- **Response model:** `ReadinessResponse` (`app/schemas/health.py`)
- **Response body:**
  ```json
  { "status": "ready" }
  ```
- **Status codes:** `200 OK`
- **Authentication:** none. Does not call Azure, AWS, OIDC, or any other external service.

**Limitations:** Only confirms that `Settings` loaded without validation errors. It does not call Azure, AWS, a database, or any other external service.

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
- **Response model:** `CommunicationAnalysisResult` (see [Request/Response Models](request-response-models.md))
- **Status codes:**
  - `200 OK` — analysis completed successfully
  - `401 Unauthorized` — missing, malformed, expired, or otherwise invalid bearer token
  - `403 Forbidden` — authenticated token lacks `communications:analyze`
  - `422 Unprocessable Entity` — request failed Pydantic/FastAPI validation
  - `500 Internal Server Error` — the AI provider failed, or the configured `AI_PROVIDER` is unsupported (see [Error Handling](error-handling.md))
  - `503 Service Unavailable` — documented in OpenAPI as a possible response for a required dependency being unavailable, via the existing `ServiceUnavailableError` exception handler; no route in this phase currently raises it

**Limitations:**
- Authentication does not persist users or sessions.
- Rate limiting is not implemented.
- Synchronous request/response only — no streaming or WebSocket support.
