"""Integration tests for Phase 7A request correlation and privacy-safe logs."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ai_provider, get_communication_analysis_service
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.main import create_app

_ANALYZE_URL = "/api/v1/communications/analyze"
_PRIVATE_BODY = "ECI_PRIVATE_BODY_SENTINEL"
_PRIVATE_SUBJECT = "ECI_PRIVATE_SUBJECT_SENTINEL"
_PRIVATE_ERROR = "ECI_PRIVATE_ERROR_SENTINEL"


class _FailingProvider(AIProvider):
    """Test double that raises a sentinel-bearing exception."""

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        raise RuntimeError(_PRIVATE_ERROR)


def _events_named(events: list[dict], name: str) -> list[dict]:
    return [event for event in events if event.get("event") == name]


def _serialized(events: list[dict]) -> str:
    return repr(events)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, log_events: list[dict]) -> Iterator[TestClient]:
    """Build a TestClient with captured structured logs."""
    del log_events
    for name in (
        "APP_NAME",
        "APP_VERSION",
        "APP_ENV",
        "APP_HOST",
        "APP_PORT",
        "LOG_LEVEL",
        "API_V1_PREFIX",
        "AI_PROVIDER",
        "FOUNDRY_PROJECT_ENDPOINT",
        "FOUNDRY_MODEL_DEPLOYMENT",
        "BEDROCK_REGION",
        "BEDROCK_MODEL_ID",
        "AUTH_MODE",
        "OIDC_ISSUER",
        "OIDC_AUDIENCE",
        "OIDC_JWKS_URL",
        "OIDC_REQUIRED_PERMISSION",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client


def _valid_payload(
    body: str,
    *,
    subject: str | None = "Status update",
    message_id: str | None = "msg-001",
) -> dict:
    payload: dict = {
        "message": {
            "body": body,
            "metadata": {
                "source_type": "email",
                "sender": "alice@example.com",
                "recipients": ["bob@example.com"],
                "subject": subject,
            },
        },
        "include_draft_reply": True,
        "include_action_items": True,
    }
    if message_id is not None:
        payload["message"]["message_id"] = message_id
    return payload


def test_successful_response_includes_unique_request_id(client: TestClient) -> None:
    """Successful responses must include a server-generated UUID request ID."""
    first = client.get("/health")
    second = client.get("/health")

    first_id = first.headers["x-request-id"]
    second_id = second.headers["x-request-id"]
    uuid.UUID(first_id)
    uuid.UUID(second_id)
    assert first_id != second_id
    assert first.json() == {"status": "healthy"}
    assert "request_id" not in first.json()


def test_incoming_request_id_is_ignored(client: TestClient) -> None:
    """The server must generate its own request ID and ignore inbound values."""
    response = client.get("/health", headers={"X-Request-ID": "client-supplied-id"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "client-supplied-id"
    uuid.UUID(response.headers["x-request-id"])


def test_request_id_correlates_api_service_and_provider_logs(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """The same request_id must appear on API, service, and provider events."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload("Sharing the notes from today's standup for visibility."),
    )

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    body = response.json()
    assert body["analysis"]["message_id"] == "msg-001"
    assert "request_id" not in body

    required_events = {
        "http_request_started",
        "http_request_completed",
        "communication_analysis_request_received",
        "communication_analysis_started",
        "communication_analysis_completed",
        "mock_analysis_requested",
        "mock_analysis_completed",
    }
    correlated = [
        event
        for event in log_events
        if event.get("event") in required_events and event.get("request_id") == request_id
    ]
    assert {event["event"] for event in correlated} == required_events

    completed = _events_named(correlated, "http_request_completed")[0]
    assert completed["method"] == "POST"
    assert completed["path"] == _ANALYZE_URL
    assert completed["status_code"] == 200
    assert isinstance(completed["duration_ms"], float)
    assert completed["duration_ms"] >= 0

    service_completed = _events_named(correlated, "communication_analysis_completed")[0]
    assert service_completed["provider"] == "mock"
    assert service_completed["message_id"] == "msg-001"
    assert service_completed["duration_ms"] >= 0

    provider_completed = _events_named(correlated, "mock_analysis_completed")[0]
    assert provider_completed["provider"] == "mock"
    assert provider_completed["duration_ms"] >= 0


def test_request_without_message_id_still_has_request_id(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """Correlation must work when the caller omits message_id."""
    payload = _valid_payload("Ordinary business update.", message_id=None)
    response = client.post(_ANALYZE_URL, json=payload)

    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    uuid.UUID(request_id)
    assert response.json()["analysis"]["message_id"] is None

    started = _events_named(log_events, "communication_analysis_started")
    assert started
    assert started[-1]["request_id"] == request_id
    assert started[-1]["message_id"] is None


def test_validation_error_includes_request_id(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """422 responses must still receive X-Request-ID and HTTP completion telemetry."""
    response = client.post(_ANALYZE_URL, json=_valid_payload("   "))

    assert response.status_code == 422
    request_id = response.headers["x-request-id"]
    uuid.UUID(request_id)
    completed = _events_named(log_events, "http_request_completed")[-1]
    assert completed["request_id"] == request_id
    assert completed["status_code"] == 422
    assert completed["duration_ms"] >= 0


def test_handled_500_preserves_request_correlation(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """Handled provider failures keep request_id on HTTP and application error logs."""
    client.app.dependency_overrides[get_ai_provider] = lambda: _FailingProvider()
    try:
        response = client.post(_ANALYZE_URL, json=_valid_payload("Hello there"))
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 500
    request_id = response.headers["x-request-id"]
    failed = _events_named(log_events, "communication_analysis_failed")[-1]
    error = _events_named(log_events, "application_error")[-1]
    completed = _events_named(log_events, "http_request_completed")[-1]
    assert failed["request_id"] == request_id
    assert failed["error_class"] == "RuntimeError"
    assert error["request_id"] == request_id
    assert error["error_class"] == "AnalysisFailedError"
    assert completed["request_id"] == request_id
    assert completed["status_code"] == 500
    assert _PRIVATE_ERROR not in _serialized(log_events)


def test_handled_503_preserves_request_correlation(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """Handled 503 responses include X-Request-ID and error_class, not exception text."""

    def _unavailable() -> None:
        raise ServiceUnavailableError(_PRIVATE_ERROR)

    client.app.dependency_overrides[get_communication_analysis_service] = _unavailable
    try:
        response = client.post(_ANALYZE_URL, json=_valid_payload("Hello there"))
    finally:
        client.app.dependency_overrides.pop(get_communication_analysis_service, None)

    assert response.status_code == 503
    request_id = response.headers["x-request-id"]
    warning = _events_named(log_events, "service_unavailable")[-1]
    completed = _events_named(log_events, "http_request_completed")[-1]
    assert warning["request_id"] == request_id
    assert warning["error_class"] == "ServiceUnavailableError"
    assert completed["status_code"] == 503
    assert _PRIVATE_ERROR not in _serialized(log_events)


def test_privacy_sentinels_are_not_logged(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """Structured logs must not contain communication content or exception text."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload(_PRIVATE_BODY, subject=_PRIVATE_SUBJECT),
    )

    assert response.status_code == 200
    serialized = _serialized(log_events)
    assert _PRIVATE_BODY not in serialized
    assert _PRIVATE_SUBJECT not in serialized
    assert "alice@example.com" not in serialized
    assert "bob@example.com" not in serialized


def test_request_context_is_cleared_between_requests(
    client: TestClient,
    log_events: list[dict],
) -> None:
    """Bound request_id must not leak from one HTTP request into the next."""
    first = client.get("/api/v1/health")
    second = client.get("/api/v1/readiness")

    first_id = first.headers["x-request-id"]
    second_id = second.headers["x-request-id"]
    assert first_id != second_id

    first_completed = [
        event
        for event in log_events
        if event.get("event") == "http_request_completed" and event.get("path") == "/api/v1/health"
    ][-1]
    second_completed = [
        event
        for event in log_events
        if event.get("event") == "http_request_completed"
        and event.get("path") == "/api/v1/readiness"
    ][-1]
    assert first_completed["request_id"] == first_id
    assert second_completed["request_id"] == second_id
    assert first.json()["status"] == "healthy"
    assert second.json() == {"status": "ready"}
