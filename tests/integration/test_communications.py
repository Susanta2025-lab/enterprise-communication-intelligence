"""Integration tests for the communication analysis REST endpoint."""

import json
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_ai_provider
from app.core.config import get_settings
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.main import create_app
from app.providers.amazon_bedrock.provider import AmazonBedrockProvider
from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider

_SETTINGS_ENV_VARS = (
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
)

_ANALYZE_URL = "/api/v1/communications/analyze"


class _FailingProvider(AIProvider):
    """Test double that always fails to simulate an upstream provider outage."""

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        raise RuntimeError("provider unreachable")


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Build a TestClient using the default (mock) provider configuration."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client


def _valid_payload(
    body: str,
    *,
    subject: str | None = "Status update",
    source_type: str = "email",
    sender: str = "alice@example.com",
    recipients: list[str] | None = None,
    message_id: str | None = "msg-001",
    include_draft_reply: bool = True,
    include_action_items: bool = True,
) -> dict:
    return {
        "message": {
            "body": body,
            "message_id": message_id,
            "metadata": {
                "source_type": source_type,
                "sender": sender,
                "recipients": recipients or ["bob@example.com"],
                "subject": subject,
            },
        },
        "include_draft_reply": include_draft_reply,
        "include_action_items": include_action_items,
    }


def test_analyze_normal_communication(client: TestClient) -> None:
    """A routine business communication should return a medium-priority analysis."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload("Sharing the notes from today's standup for visibility."),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert payload["analysis"]["priority"]["level"] == "medium"
    assert payload["analysis"]["category"] == "general"


def test_analyze_urgent_communication(client: TestClient) -> None:
    """Urgent language should raise the returned priority."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload("This is urgent and needs attention ASAP."),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["priority"]["level"] == "high"


def test_analyze_generates_action_item(client: TestClient) -> None:
    """Action-oriented language should produce at least one action item."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload(
            "Please review the proposal and schedule a meeting before the deadline.",
            subject="Proposal review",
        ),
    )

    assert response.status_code == 200
    action_items = response.json()["analysis"]["action_items"]
    assert len(action_items) == 1
    assert action_items[0]["description"] == "Follow up on: Proposal review"


def test_analyze_generates_draft_reply(client: TestClient) -> None:
    """Draft replies should be included by default."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload("Thanks for the update, no action needed."),
    )

    assert response.status_code == 200
    draft_reply = response.json()["analysis"]["draft_reply"]
    assert draft_reply is not None
    assert draft_reply["body"]


def test_analyze_rejects_empty_message_body(client: TestClient) -> None:
    """An empty message body must fail request validation."""
    response = client.post(_ANALYZE_URL, json=_valid_payload("   "))

    assert response.status_code == 422


def test_analyze_rejects_invalid_source_type(client: TestClient) -> None:
    """An unknown source type must fail request validation."""
    response = client.post(
        _ANALYZE_URL,
        json=_valid_payload("Hello there", source_type="carrier-pigeon"),
    )

    assert response.status_code == 422


def test_analyze_rejects_malformed_payload(client: TestClient) -> None:
    """A payload missing required fields must fail request validation."""
    response = client.post(_ANALYZE_URL, json={"message": {"body": "Hello"}})

    assert response.status_code == 422


def test_analyze_rejects_unknown_fields(client: TestClient) -> None:
    """Unexpected top-level fields must be rejected by the strict domain schema."""
    payload = _valid_payload("Hello there")
    payload["unexpected_field"] = "should not be allowed"

    response = client.post(_ANALYZE_URL, json=payload)

    assert response.status_code == 422


def test_analyze_translates_provider_failure_to_error_response(
    client: TestClient,
) -> None:
    """Provider failures must surface as a translated application error, not a trace."""
    client.app.dependency_overrides[get_ai_provider] = lambda: _FailingProvider()
    try:
        response = client.post(_ANALYZE_URL, json=_valid_payload("Hello there"))
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 500
    payload = response.json()
    assert set(payload) == {"detail"}
    assert "traceback" not in payload["detail"].lower()
    assert "failed to analyze" in payload["detail"].lower()


def test_analyze_rejects_unsupported_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unsupported AI_PROVIDER value must fail explicitly, not silently fall back."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "azure")

    with TestClient(create_app()) as unsupported_client:
        response = unsupported_client.post(
            _ANALYZE_URL, json=_valid_payload("Hello there")
        )

    assert response.status_code == 500
    payload = response.json()
    assert set(payload) == {"detail"}
    assert "unsupported ai provider" in payload["detail"].lower()


def test_analyze_error_response_hides_implementation_details(
    client: TestClient,
) -> None:
    """Error responses must never include stack traces or internal exception types."""
    client.app.dependency_overrides[get_ai_provider] = lambda: _FailingProvider()
    try:
        response = client.post(_ANALYZE_URL, json=_valid_payload("Hello there"))
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    body_text = response.text.lower()
    assert "runtimeerror" not in body_text
    assert "traceback" not in body_text
    assert "site-packages" not in body_text


def test_analyze_with_mocked_microsoft_foundry_provider(client: TestClient) -> None:
    """API analysis should succeed with a mocked Microsoft Foundry provider."""
    mock_openai = MagicMock()
    mock_openai.responses.create.return_value = SimpleNamespace(
        output_text=json.dumps(
            {
                "summary_text": "The sender asked for a review of the weekly report.",
                "summary_confidence": 0.9,
                "priority_level": "medium",
                "priority_rationale": "Routine review request.",
                "priority_confidence": 0.7,
                "category": "request",
                "action_items": [
                    {
                        "description": "Review the weekly report",
                        "owner": "bob@example.com",
                        "due_at": None,
                        "priority": "medium",
                    }
                ],
                "draft_reply": {
                    "body": "Thank you. I will review the weekly report.",
                    "tone": "neutral",
                    "confidence": 0.8,
                },
            }
        )
    )
    provider = MicrosoftFoundryProvider(
        project_endpoint=(
            "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
        ),
        model_deployment="eci-gpt-54-mini",
        openai_client=mock_openai,
    )
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        response = client.post(
            _ANALYZE_URL,
            json=_valid_payload("Please review the weekly status report."),
        )
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "microsoft_foundry"
    assert payload["analysis"]["summary"]["text"] == (
        "The sender asked for a review of the weekly report."
    )
    assert payload["analysis"]["priority"]["level"] == "medium"
    assert payload["analysis"]["category"] == "request"


def test_analyze_with_mocked_amazon_bedrock_provider(client: TestClient) -> None:
    """API analysis should succeed with a mocked Amazon Bedrock provider."""
    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "summary_text": (
                                    "The sender asked for a review of the weekly report."
                                ),
                                "summary_confidence": 0.9,
                                "priority_level": "medium",
                                "priority_rationale": "Routine review request.",
                                "priority_confidence": 0.7,
                                "category": "request",
                                "action_items": [
                                    {
                                        "description": "Review the weekly report",
                                        "owner": "bob@example.com",
                                        "due_at": None,
                                        "priority": "medium",
                                    }
                                ],
                                "draft_reply": {
                                    "body": "Thank you. I will review the weekly report.",
                                    "tone": "neutral",
                                    "confidence": 0.8,
                                },
                            }
                        )
                    }
                ]
            }
        }
    }
    provider = AmazonBedrockProvider(
        region="eu-south-2",
        model_id="eu.anthropic.claude-haiku-4-5-20251001-v1:0",
        bedrock_runtime_client=mock_client,
    )
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        response = client.post(
            _ANALYZE_URL,
            json=_valid_payload("Please review the weekly status report."),
        )
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "amazon_bedrock"
    assert payload["analysis"]["summary"]["text"] == (
        "The sender asked for a review of the weekly report."
    )
    assert payload["analysis"]["priority"]["level"] == "medium"
    assert payload["analysis"]["category"] == "request"
