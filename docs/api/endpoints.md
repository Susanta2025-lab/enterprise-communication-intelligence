# Endpoints

All HTTP endpoints implemented in the repository as of completed Phase 13. Phase 10 added **no** connector message-ingestion HTTP endpoints. There is no `/api/v1/connectors` route. Connector fetch capability currently exists below the HTTP product surface. Phase 13 adds mailbox OAuth lifecycle HTTP (authorize, callback, disconnect, reauthorize), not message ingestion.

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

Cross-user access is indistinguishable from an unknown id.

---

## `POST /api/v1/workflow-actions`

**Purpose:** Create a PENDING reply workflow action by snapshotting the draft reply from an analysis owned by the authenticated caller.

- **Method:** `POST`
- **Path:** `{API_V1_PREFIX}/workflow-actions` → `/api/v1/workflow-actions` by default
- **Request requirements:**
  - `Content-Type: application/json`
  - Body must conform to `WorkflowActionCreateRequest`: `{ "analysis_id": "<uuid>" }`
  - Unknown fields are rejected (`extra="forbid"`)
  - Callers cannot supply `action_type`, `status`, `proposed_reply_body`, `approved_reply_body`, ownership, or timestamps
- **Authentication:** always required. Uses `require_authenticated_communications_workflow`: `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, send `Authorization: Bearer <JWT>` with permission `communications:workflow`.
- **Response model:** `WorkflowActionResponse`
- **Status codes:**
  - `201 Created` — pending workflow action created; `proposed_reply_body` is the draft snapshot; `approved_reply_body` is `null`; `has_execution_target` is `true` only when mailbox routing provenance was snapshotted. That flag does not mean a real provider can send the message.
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `404 Not Found` — analysis unknown or not owned by the caller. Body: `{"detail": "Analysis not found."}`
  - `409 Conflict` — analysis has no usable draft reply. Body: `{"detail": "Analysis has no usable draft reply."}`
  - `422` — invalid UUID or extra fields
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

The same `analysis_id` may create multiple workflow actions. The route does not load the analysis, resolve `user_id`, or open a unit of work; `WorkflowActionService.create` owns that behavior.

---

## `GET /api/v1/workflow-actions`

**Purpose:** Return a bounded page of workflow actions owned by the authenticated caller.

- **Method:** `GET`
- **Path:** `{API_V1_PREFIX}/workflow-actions` → `/api/v1/workflow-actions` by default
- **Query parameters:** `limit` (1–100, default 20), `offset` (>= 0, default 0)
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:workflow`.
- **Response model:** `WorkflowActionListResponse`
- **Status codes:**
  - `200 OK` — page of owned items; callers without an identity mapping receive an empty page
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

Ordering is repository `created_at DESC, id DESC`. The response is `{ "items": [...], "limit": ..., "offset": ... }`. Total count is omitted. `owner_user_id` is not exposed.

---

## `GET /api/v1/workflow-actions/{action_id}`

**Purpose:** Return one workflow action owned by the authenticated caller.

- **Method:** `GET`
- **Path:** `/api/v1/workflow-actions/{action_id}`
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:workflow`.
- **Response model:** `WorkflowActionResponse`
- **Status codes:**
  - `200 OK` — owned workflow action, including when the referenced analysis has been deleted
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `404 Not Found` — unknown id or owned by a different user. Body: `{"detail": "Workflow action not found."}`
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

The stored `analysis_id` is returned without dereferencing the analysis.

---

## `POST /api/v1/workflow-actions/{action_id}/approve`

**Purpose:** Approve a PENDING workflow action owned by the authenticated caller.

- **Method:** `POST`
- **Path:** `/api/v1/workflow-actions/{action_id}/approve`
- **Request body:** none. Do not send approved reply text.
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:workflow`.
- **Response model:** `WorkflowActionResponse`
- **Status codes:**
  - `200 OK` — status `approved`; `approved_reply_body` copied from `proposed_reply_body`; `approved_at` populated
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `404 Not Found` — unknown id or owned by a different user
  - `409 Conflict` — invalid transition or concurrent update
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

Repeated approve is not idempotent. Approving an already approved or rejected action returns `409`. Approval still succeeds after the source analysis is deleted. Approval copies the stored proposal into `approved_reply_body`; it does not call `CommunicationActionExecutor` and does not send mail.

---

## `POST /api/v1/workflow-actions/{action_id}/reject`

**Purpose:** Reject a PENDING workflow action owned by the authenticated caller.

- **Method:** `POST`
- **Path:** `/api/v1/workflow-actions/{action_id}/reject`
- **Request body:** none. Rejection reason is not accepted.
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:workflow`.
- **Response model:** `WorkflowActionResponse`
- **Status codes:**
  - `200 OK` — status `rejected`; `proposed_reply_body` retained; `approved_reply_body` remains `null`; `rejected_at` populated
  - `401` / `403` — authentication/authorization failure (`AUTH_MODE=disabled` is `401`)
  - `404 Not Found` — unknown id or owned by a different user
  - `409 Conflict` — invalid transition or concurrent update
  - `503` — persistence unavailable, including when `DATABASE_URL` is omitted

Repeated reject is not idempotent. Rejecting an already rejected or approved action returns `409`. Rejection still succeeds after the source analysis is deleted. A rejected action cannot execute.

---

## `POST /api/v1/workflow-actions/{action_id}/execute`

**Purpose:** Execute an owned APPROVED workflow action through the mailbox account snapshotted at proposal time. This is explicit user-approved execution, not an automatic reply.

- **Method:** `POST`
- **Path:** `/api/v1/workflow-actions/{action_id}/execute`
- **Request body:** none. Callers cannot supply reply text, provider, connector account, credentials, or a provider message id.
- **Authentication:** always required. Uses `require_authenticated_communications_send`: `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, send `Authorization: Bearer <JWT>` with permission `communications:send`.
- **Response model:** `WorkflowActionResponse`
- **Status codes:**
  - `200 OK` — terminal `executed` or `failed` resource.
    - `executed` means Graph accepted `/reply` with 202, or Gmail accepted profile + metadata + send with 200, and that outcome was stored.
    - `failed` means the provider definitely rejected the send (completed 3xx or non-408 4xx) and that outcome was stored. HTTP 200 + FAILED is a completed execution request, not a transport failure.
  - `401` — missing or invalid bearer token (`AUTH_MODE=disabled` included)
  - `403` — authenticated caller lacks `communications:send`
  - `404 Not Found` — unknown id or owned by a different user. Body: `{"detail": "Workflow action not found."}`
  - `409 Conflict` — not APPROVED, already `executing`/`executed`/`failed`, not executable, or concurrent update. Body for not-executable: `{"detail": "Workflow action is not executable."}`
  - `503` — persistence unavailable before TX1 (prior status unchanged; execution did not reach the provider stage), missing mailbox secret after TX1 (stored `executing`; the provider request did not occur), Gmail pre-send unavailability, or uncertain provider outcome after TX1. HTTP 503 + EXECUTING means ECI cannot safely establish or complete execution; do not retry automatically. Not every 503 means a provider send may have occurred.

Unauthorized and forbidden requests do not open an execution unit of work, resolve credentials, retrieve tokens, or call the mailbox provider. Create, list, get, approve, and reject remain `communications:workflow`. Provider-specific error bodies are not returned. There is no retry route. Explicit OAuth accounts without `mail.send` are not executable (`409`); legacy `granted_capabilities=NULL` accounts keep Phase 12 eligibility.

---

## `POST /api/v1/connector-accounts/gmail/authorize`

**Purpose:** Start a server-side Gmail mailbox consent session and return the Google authorization URL. This is mailbox OAuth, not ECI login.

- **Method:** `POST`
- **Path:** `/api/v1/connector-accounts/gmail/authorize`
- **Request body:** none. Callers cannot supply scopes, redirect URI, state, PKCE, or `credential_ref`.
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:connect`.
- **Response model:** `GmailAuthorizationStartResponse` (`authorization_url`, `expires_at`)
- **Status codes:**
  - `200 OK` — Google authorization URL for the browser
  - `401` / `403` — authentication/authorization failure
  - `400` — mailbox authorization could not be started
  - `503` — Gmail OAuth is unconfigured, persistence is unavailable, production lacks a durable credential store, or the configured store is unavailable

Authorization runs before unit-of-work, OAuth adapter, and credential-store construction. Raw state, PKCE verifier, and client secret are not returned.

---

## `GET /api/v1/oauth/callbacks/gmail`

**Purpose:** Google redirect target for Gmail mailbox consent. Ownership comes from the Phase 13A authorization session.

- **Method:** `GET`
- **Path:** `/api/v1/oauth/callbacks/gmail`
- **Query:** `code`, `state`, and `error` when Google supplies them. `user_id`, email, `credential_ref`, and scopes are ignored even if present.
- **Authentication:** none. This is not an ECI bearer-token route.
- **Response model:** `GmailAuthorizationCallbackResponse` (`provider`, `connector_account_id`, `external_account_id`, `status`, `granted_capabilities`)
- **Status codes:**
  - `200 OK` — Gmail connector account created, reactivated, or reused
  - `400` — invalid/expired/consumed state, consent denied, missing refresh token, invalid ID token, or missing `mail.read`
  - `503` — Gmail OAuth unavailable, persistence failure, or credential-store compensation failure

Invalid state does not call Google. Consent denial consumes the session and does not exchange a token. Tokens are never returned. Live Google Cloud setup remains an external operator step; automated tests mock Google.

---

## `POST /api/v1/connector-accounts/microsoft_graph/authorize`

**Purpose:** Start a server-side Microsoft mailbox consent session and return the Microsoft identity platform authorization URL. This is mailbox OAuth, not ECI login.

- **Method:** `POST`
- **Path:** `/api/v1/connector-accounts/microsoft_graph/authorize`
- **Request body:** none. Callers cannot supply scopes, redirect URI, state, PKCE, or `credential_ref`.
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:connect`.
- **Response model:** `MicrosoftAuthorizationStartResponse` (`authorization_url`, `expires_at`)
- **Status codes:**
  - `200 OK` — Microsoft authorization URL for the browser
  - `401` / `403` — authentication/authorization failure
  - `400` — mailbox authorization could not be started
  - `503` — Microsoft OAuth is unconfigured, persistence is unavailable, production lacks a durable credential store, or the configured store is unavailable

Authorization runs before unit-of-work, OAuth adapter, and credential-store construction. Raw state, PKCE verifier, and client secret are not returned.

---

## `GET /api/v1/oauth/callbacks/microsoft_graph`

**Purpose:** Microsoft redirect target for Graph mailbox consent. Ownership comes from the Phase 13A authorization session.

- **Method:** `GET`
- **Path:** `/api/v1/oauth/callbacks/microsoft_graph`
- **Query:** `code`, `state`, and `error` when Microsoft supplies them. `user_id`, email, `credential_ref`, and scopes are ignored even if present.
- **Authentication:** none. This is not an ECI bearer-token route.
- **Response model:** `MicrosoftAuthorizationCallbackResponse` (`provider`, `connector_account_id`, `external_account_id`, `status`, `granted_capabilities`)
- **Status codes:**
  - `200 OK` — Microsoft Graph connector account created, reactivated, or reused
  - `400` — invalid/expired/consumed state, consent denied, missing refresh token, invalid ID token, or missing `mail.read`
  - `503` — Microsoft OAuth unavailable, persistence failure, or credential-store compensation failure

Invalid state does not call Microsoft. Consent denial consumes the session and does not exchange a token. Tokens are never returned. CONNECT creates or reuses an account by verified `{tid}:{oid}`. REAUTHORIZE attaches a new credential only to the bound account and only when the verified identity matches. Automated tests mock Microsoft.

---

## `POST /api/v1/connector-accounts/{connector_account_id}/disconnect`

**Purpose:** Remove ECI's stored delegated mailbox credential for an owned account and mark it disconnected. This is the authoritative ECI security boundary. It is not an automatic reply and not provider-wide session revocation.

- **Method:** `POST`
- **Path:** `/api/v1/connector-accounts/{connector_account_id}/disconnect`
- **Request body:** none
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:connect`.
- **Response model:** `ConnectorAccountResponse` (`id`, `provider`, `external_account_id`, `status`, `granted_capabilities`, `created_at`, `updated_at`)
- **Status codes:**
  - `200 OK` — account is `disconnected`; locator and grants are null
  - `401` / `403` — authentication/authorization failure
  - `404` — unknown id or not owned. Body: `{"detail": "Connector account not found."}`
  - `503` — persistence or credential store unavailable while removal is required

Ownership is verified before secret-store operations. Repeated disconnect is idempotent. `credential_ref` is never returned. Google grant revocation is best-effort after local credential removal. Microsoft-side application consent is not revoked (`revokeSignInSessions` is not called).

---

## `POST /api/v1/connector-accounts/{connector_account_id}/reauthorize`

**Purpose:** Start a server-side mailbox consent session bound to an existing owned connector account. The account's stored provider is used. Callers cannot switch provider or supply scopes.

- **Method:** `POST`
- **Path:** `/api/v1/connector-accounts/{connector_account_id}/reauthorize`
- **Request body:** none
- **Authentication:** always required. `AUTH_MODE=disabled` returns `401`. When `AUTH_MODE=oidc`, permission `communications:connect`.
- **Response model:** `ConnectorAccountReauthorizeResponse` (`authorization_url`, `expires_at`)
- **Status codes:**
  - `200 OK` — provider authorization URL for the browser
  - `401` / `403` — authentication/authorization failure
  - `404` — unknown id or not owned
  - `409` — account is `ACTIVE` or otherwise not reauthorizable. Body: `{"detail": "Connector account cannot be updated."}`
  - `400` — mailbox reauthorization could not be started
  - `503` — provider OAuth or persistence unavailable

`DISCONNECTED` and `REAUTH_REQUIRED` are accepted. The callback remains unauthenticated. Successful reauthorization reactivates the exact bound account to `ACTIVE` with a new opaque locator and freshly granted capabilities. Selecting a different mailbox at consent is rejected.

---

## Direct-text analyze versus connected-mailbox analyze

`POST /api/v1/communications/analyze` remains the direct-text path. It requires only `communications:analyze`, does not use connector accounts, and does not call mailbox connectors.

The connected-mailbox product flow is:

```text
connected mailbox
→ GET .../messages (bounded list)
→ user selects one provider_message_id
→ POST .../messages/analyze
```

Listing is a bounded request/response read-through. It is not mailbox synchronization, not a local mailbox mirror, not searchable, and does not return attachments, full bodies, or background ingestion.

### `GET /api/v1/connector-accounts/{connector_account_id}/messages`

Served in Phase 14D.

- **Authorization:** authenticated principal + `communications:read`. `AUTH_MODE=disabled` returns `401`. `communications:analyze` is not required.
- **Query:** `ConnectorAccountMessageListQuery` — `page_size` (default 10, maximum 100) and opaque `cursor`
- **Response:** `ConnectorAccountMessageListResponse` — `items` plus `next_cursor` (`null` on the last page)
- **List item fields:** `provider_message_id`, `sender`, `subject`, `sent_at`, `received_at`
- **Not returned:** full body, attachments, `thread_id`, `credential_ref`, tokens, OAuth data, raw provider JSON, Graph `nextLink` or other vendor pagination URLs
- **Status codes:** `401` unauthenticated; `403` missing `communications:read`; `404` unknown or not-owned connector account; `409` owned account not currently usable; `400` invalid/expired pagination cursor when the connector identifies that condition; `422` invalid query; `503` transient unavailability
- **Behavior:** ownership and mailbox usability are established before credential I/O or mailbox HTTP. One list request corresponds to one bounded connector page. Messages are not persisted. AI is not invoked. No workflow action is created and no send/reply occurs.

### `POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze`

Served in Phase 14C.

- **Authorization:** authenticated principal + `communications:read` + `communications:analyze`. `AUTH_MODE=disabled` returns `401`. `communications:send` is not required.
- **Request body:** `ConnectorAccountMessageAnalyzeRequest` — `{ "provider_message_id": "<opaque>" }`
- **Response:** existing `CommunicationAnalysisResponse` (`analysis`, `provider`, optional `analysis_id`)
- **Not returned:** raw message body, `credential_ref`, tokens, or provider OAuth metadata
- **Status codes:** `401` unauthenticated; `403` missing read or analyze; `404` unknown/not-owned account or unknown provider message; `409` owned account not currently usable; `422` invalid body; `500` unexpected normalization/internal failure; `503` transient credential/provider unavailability
- **Behavior:** ownership and mailbox usability are established before credential I/O, mailbox HTTP, or AI. Draft replies remain suggestions. No workflow action is created and no send/reply occurs.
