# Examples

All examples assume the server is running locally with default configuration (`AI_PROVIDER=mock`):

```bash
uvicorn app.main:app --reload
```

Base URL: `http://localhost:8000`

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
{"status": "healthy", "service": "ContextMesh", "version": "0.1.0", "environment": "development"}
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

Returns a `medium` priority, `general` category analysis with no action items, since no urgent or action-oriented keywords are present (see `app/providers/mock/provider.py`).

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
