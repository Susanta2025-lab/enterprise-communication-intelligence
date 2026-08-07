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
    "service": "ContextMesh",
    "version": "0.1.0",
    "environment": "development"
  }
  ```
  `service`, `version`, and `environment` are read from `Settings` (`app_name`, `app_version`, `app_env`).
- **Status codes:** `200 OK`

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

**Limitations:** Only confirms that `Settings` loaded without validation errors. It does not call Azure, AWS, a database, or any other external service — there are none to check in this phase.

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
- **Response model:** `CommunicationAnalysisResult` (see [Request/Response Models](request-response-models.md))
- **Status codes:**
  - `200 OK` — analysis completed successfully
  - `422 Unprocessable Entity` — request failed Pydantic/FastAPI validation
  - `500 Internal Server Error` — the AI provider failed, or the configured `AI_PROVIDER` is unsupported (see [Error Handling](error-handling.md))
  - `503 Service Unavailable` — documented in OpenAPI as a possible response for a required dependency being unavailable, via the existing `ServiceUnavailableError` exception handler; no route in this phase currently raises it

**Limitations:**
- Only the mock provider is available; results are deterministic keyword-based heuristics, not a real language model.
- No authentication, rate limiting, or persistence of requests/results.
- Synchronous request/response only — no streaming or WebSocket support.
