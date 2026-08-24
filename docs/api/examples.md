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

## Disconnect (requires OIDC)

```bash
curl -sS -X POST http://localhost:8000/api/v1/connector-accounts/<connector-account-id>/disconnect \
  -H "Authorization: Bearer <access-token-with-communications:connect>"
```

The JSON includes `id`, `provider`, `external_account_id`, `status`, `granted_capabilities`, and timestamps. It omits `credential_ref` and tokens.

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
