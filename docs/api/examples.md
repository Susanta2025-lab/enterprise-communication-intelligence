# Examples

All examples assume the server is running locally with default configuration (`AI_PROVIDER=mock`, `AUTH_MODE=disabled`):

```bash
uvicorn app.main:app --reload
```

Base URL: `http://localhost:8000`

When `AUTH_MODE=oidc`, analysis requests also need:

```bash
-H "Authorization: Bearer <access-token>"
```

Health and readiness examples remain unchanged; they do not require a token.

## Health

```bash
curl -sS http://localhost:8000/health
```

```json
{"status": "healthy"}
```

## Versioned Health

```bash
curl -sS http://localhost:8000/api/v1/health
```

```json
{"status": "healthy", "service": "Enterprise Communication Intelligence Platform", "version": "0.1.0", "environment": "development"}
```

## Readiness

```bash
curl -sS http://localhost:8000/api/v1/readiness
```

```json
{"status": "ready"}
```

## Normal Communication Analysis

```bash
curl -sS -X POST http://localhost:8000/api/v1/communications/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "Sharing the notes from today'"'"'s standup for visibility.",
      "message_id": "msg-001",
      "metadata": {
        "source_type": "email",
        "sender": "alice@example.com",
        "recipients": ["team@example.com"],
        "subject": "Standup notes"
      }
    }
  }'
```

Returns a `medium` priority, `general` category analysis with no action items, since no urgent or action-oriented keywords are present (see `app/providers/mock/provider.py`). With default local configuration (`DATABASE_URL` omitted), `analysis_id` is not present.

## Analysis History

History endpoints always require an authenticated principal (`AUTH_MODE=disabled` returns `401`). They return structured results only; they never return the original communication body. Without `DATABASE_URL`, history returns `503`.

```bash
curl -sS http://localhost:8000/api/v1/analyses \
  -H "Authorization: Bearer <access-token>"
```

```bash
curl -sS http://localhost:8000/api/v1/analyses/<analysis-id> \
  -H "Authorization: Bearer <access-token>"
```

```bash
curl -sS -X DELETE http://localhost:8000/api/v1/analyses/<analysis-id> \
  -H "Authorization: Bearer <access-token>"
```

Unknown and cross-user ids both return `404`. Do not send real bearer tokens in committed documentation or over AWS HTTP.

## Workflow Actions

Workflow proposal/approval endpoints always require an authenticated principal with `communications:workflow` (`AUTH_MODE=disabled` returns `401`). Execute requires `communications:send`. Without `DATABASE_URL`, they return `503`. Create accepts only `analysis_id`. Approve, reject, and execute have no request body.

```bash
curl -sS -X POST http://localhost:8000/api/v1/workflow-actions \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{"analysis_id": "<analysis-id>"}'
```

```bash
curl -sS http://localhost:8000/api/v1/workflow-actions \
  -H "Authorization: Bearer <access-token>"
```

```bash
curl -sS http://localhost:8000/api/v1/workflow-actions/<action-id> \
  -H "Authorization: Bearer <access-token>"
```

```bash
curl -sS -X POST http://localhost:8000/api/v1/workflow-actions/<action-id>/approve \
  -H "Authorization: Bearer <access-token>"
```

```bash
curl -sS -X POST http://localhost:8000/api/v1/workflow-actions/<action-id>/reject \
  -H "Authorization: Bearer <access-token>"
```

```bash
curl -sS -X POST http://localhost:8000/api/v1/workflow-actions/<action-id>/execute \
  -H "Authorization: Bearer <access-token>"
```

Unknown and cross-user workflow actions both return `404`. Responses omit `owner_user_id`. Execute 200 with `status=failed` means a definite provider rejection was stored. Execute 503 before TX1 leaves the previous workflow state unchanged and does not reach the provider. Execute 503 after TX1 means the row remains `executing` and must not be retried automatically; a missing mailbox secret in that window means the provider request did not occur. Not every 503 means a send may have occurred. There is no retry, PATCH, or DELETE workflow route.

## Urgent Communication

```bash
curl -sS -X POST http://localhost:8000/api/v1/communications/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "This is urgent and needs attention ASAP.",
      "message_id": "msg-002",
      "metadata": {
        "source_type": "email",
        "sender": "alice@example.com",
        "recipients": ["bob@example.com"]
      }
    }
  }'
```

The mock provider detects the keyword `urgent`/`asap` and returns `"priority": {"level": "high", "rationale": "Detected urgent language.", ...}`.

## Action-Item Extraction

```bash
curl -sS -X POST http://localhost:8000/api/v1/communications/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "Please review the proposal and schedule a meeting before the deadline.",
      "message_id": "msg-003",
      "metadata": {
        "source_type": "email",
        "sender": "alice@example.com",
        "recipients": ["bob@example.com"],
        "subject": "Proposal review"
      }
    }
  }'
```

The mock provider detects action-oriented keywords (`schedule`, `deadline`, `please review`) and returns one action item:

```json
"action_items": [
  {
    "description": "Follow up on: Proposal review",
    "owner": "bob@example.com",
    "due_at": null,
    "priority": "high"
  }
]
```

## Draft Reply Generation

Draft replies are included by default (`include_draft_reply: true`):

```bash
curl -sS -X POST http://localhost:8000/api/v1/communications/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "Thanks for the update, no action needed.",
      "message_id": "msg-004",
      "metadata": {
        "source_type": "email",
        "sender": "alice@example.com",
        "recipients": ["bob@example.com"]
      }
    }
  }'
```

The response includes a `draft_reply` object with a short, neutral `body` whose wording depends on the assigned priority level.

To omit the draft reply:

```bash
curl -sS -X POST http://localhost:8000/api/v1/communications/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "Thanks for the update, no action needed.",
      "metadata": {"source_type": "email", "sender": "alice@example.com"}
    },
    "include_draft_reply": false
  }'
```

## Validation Failure

An empty message body is rejected with `422`:

```bash
curl -sS -X POST http://localhost:8000/api/v1/communications/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "body": "   ",
      "metadata": {"source_type": "email", "sender": "alice@example.com"}
    }
  }'
```

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "message", "body"],
      "msg": "Value error, body must not be empty",
      "input": "   "
    }
  ]
}
```

(Exact `loc`/`msg` values follow FastAPI's standard Pydantic v2 error format.)

## Gmail mailbox authorize (requires OIDC)

`POST /api/v1/connector-accounts/gmail/authorize` always requires an authenticated principal. `AUTH_MODE=disabled` returns `401`. The Google callback is public and is not shown with a bearer token.

```bash
curl -sS -X POST http://localhost:8000/api/v1/connector-accounts/gmail/authorize \
  -H "Authorization: Bearer <access-token-with-communications:connect>"
```

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
  "expires_at": "2026-08-23T12:10:00+00:00"
}
```

The JSON omits state, PKCE verifier, client secret, and tokens.

## Owned connector accounts (requires OIDC)

`GET /api/v1/connector-accounts` always requires an authenticated principal with `communications:read`. `AUTH_MODE=disabled` returns `401`. Callers without an identity mapping receive an empty page.

```bash
curl -sS "http://localhost:8000/api/v1/connector-accounts?limit=20&offset=0" \
  -H "Authorization: Bearer <access-token-with-communications:read>"
```

```json
{
  "items": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "provider": "gmail",
      "status": "active",
      "granted_capabilities": ["mail.read", "mail.send"],
      "created_at": "2026-08-25T00:00:00+00:00",
      "updated_at": "2026-08-25T00:00:00+00:00"
    }
  ],
  "limit": 20,
  "offset": 0
}
```

The JSON omits `credential_ref`, `external_account_id`, locators, and tokens.

## Disconnect (requires OIDC)

```bash
curl -sS -X POST http://localhost:8000/api/v1/connector-accounts/<connector-account-id>/disconnect \
  -H "Authorization: Bearer <access-token-with-communications:connect>"
```

The JSON includes `id`, `provider`, `status`, `granted_capabilities`, and timestamps. It omits `credential_ref`, `external_account_id`, and tokens.

## Reauthorize (requires OIDC)

```bash
curl -sS -X POST http://localhost:8000/api/v1/connector-accounts/<connector-account-id>/reauthorize \
  -H "Authorization: Bearer <access-token-with-communications:connect>"
```

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/auth?...",
  "expires_at": "2026-08-24T12:10:00+00:00"
}
```

`ACTIVE` accounts return `409`. Callbacks remain unauthenticated.

## Microsoft mailbox authorize (requires OIDC)

`POST /api/v1/connector-accounts/microsoft_graph/authorize` always requires an authenticated principal. `AUTH_MODE=disabled` returns `401`. The Microsoft callback is public and is not shown with a bearer token.

```bash
curl -sS -X POST http://localhost:8000/api/v1/connector-accounts/microsoft_graph/authorize \
  -H "Authorization: Bearer <access-token-with-communications:connect>"
```

```json
{
  "authorization_url": "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?...",
  "expires_at": "2026-08-23T12:10:00+00:00"
}
```

The JSON omits state, PKCE verifier, client secret, and tokens. Live Entra consent is an operator step outside automated tests.

## Bounded mailbox listing (requires OIDC)

`GET /api/v1/connector-accounts/{connector_account_id}/messages` always requires an authenticated principal with `communications:read`. `AUTH_MODE=disabled` returns `401`. Listing returns provider-neutral metadata only. It does not return bodies, tokens, `credential_ref`, or provider pagination URLs.

```bash
curl -sS "http://localhost:8000/api/v1/connector-accounts/<connector-account-id>/messages?page_size=1" \
  -H "Authorization: Bearer <access-token-with-communications:read>"
```

```json
{
  "items": [
    {
      "provider_message_id": "<opaque-provider-message-id>",
      "sender": "manager@example.com",
      "subject": "Project update",
      "sent_at": "2026-08-24T12:00:00+00:00",
      "received_at": "2026-08-24T12:00:01+00:00"
    }
  ],
  "next_cursor": "<opaque-cursor-or-null>"
}
```

Continue with the opaque `next_cursor` as `cursor`. Do not parse it. Graph `@odata.nextLink` is not returned.

## Selected-message analyze (requires OIDC)

`POST /api/v1/connector-accounts/{connector_account_id}/messages/analyze` always requires an authenticated principal with both `communications:read` and `communications:analyze`. Direct-text `POST /api/v1/communications/analyze` remains a separate route and does not require `communications:read`. Analyze does not create a `WorkflowAction` and does not send mail.

```bash
curl -sS -X POST http://localhost:8000/api/v1/connector-accounts/<connector-account-id>/messages/analyze \
  -H "Authorization: Bearer <access-token-with-communications:read-and-analyze>" \
  -H "Content-Type: application/json" \
  -d '{"provider_message_id": "<opaque-provider-message-id>"}'
```

The response reuses `CommunicationAnalysisResponse`. It may include `analysis_id` when authenticated history storage succeeds. It omits raw mailbox bodies, tokens, and `credential_ref`.
