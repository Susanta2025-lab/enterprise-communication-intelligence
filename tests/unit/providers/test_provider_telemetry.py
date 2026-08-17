"""Unit tests for provider-layer operational telemetry."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.providers.amazon_bedrock.provider import AmazonBedrockProvider
from app.providers.common.output import AnalysisOutputError
from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider
from app.providers.mock.provider import MockAIProvider
from tests.unit.providers.conftest import RequestFactory

_FOUNDRY_ENDPOINT = (
    "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
)
_FOUNDRY_DEPLOYMENT = "eci-gpt-54-mini"
_BEDROCK_REGION = "eu-south-2"
_BEDROCK_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
_PRIVATE_ERROR = "ECI_PRIVATE_ERROR_SENTINEL"


def _valid_payload() -> dict:
    return {
        "summary_text": "The sender asked Bob to review the weekly status report.",
        "summary_confidence": 0.9,
        "priority_level": "high",
        "priority_rationale": "The message requests a timely review.",
        "priority_confidence": 0.8,
        "category": "request",
        "action_items": [],
        "draft_reply": {
            "body": "Thank you. I will review the weekly status report and follow up.",
            "tone": "neutral",
            "confidence": 0.85,
        },
    }


def _events_named(events: list[dict], name: str) -> list[dict]:
    return [event for event in events if event.get("event") == name]


def test_mock_provider_emits_requested_and_completed_events(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Mock analysis should emit requested and completed telemetry."""
    provider = MockAIProvider()
    result = provider.analyze(make_request("Please review the weekly status report."))

    assert result.provider == "mock"
    requested = _events_named(log_events, "mock_analysis_requested")[-1]
    completed = _events_named(log_events, "mock_analysis_completed")[-1]
    assert requested["provider"] == "mock"
    assert requested["message_id"] == "msg-001"
    assert completed["provider"] == "mock"
    assert isinstance(completed["duration_ms"], float)
    assert completed["duration_ms"] >= 0


def test_mock_provider_emits_failed_event(
    make_request: RequestFactory,
    log_events: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock failures should log error_class without the exception message."""

    def _boom(_haystack: str) -> None:
        raise RuntimeError(_PRIVATE_ERROR)

    monkeypatch.setattr("app.providers.mock.provider._classify_priority", _boom)
    provider = MockAIProvider()

    with pytest.raises(RuntimeError, match=_PRIVATE_ERROR):
        provider.analyze(make_request("Please review the weekly status report."))

    failed = _events_named(log_events, "mock_analysis_failed")[-1]
    assert failed["provider"] == "mock"
    assert failed["error_class"] == "RuntimeError"
    assert failed["duration_ms"] >= 0
    assert _PRIVATE_ERROR not in repr(failed)


def test_foundry_provider_emits_requested_and_completed_events(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Foundry success should emit requested and completed events without network I/O."""
    mock_openai = MagicMock()
    mock_openai.responses.create.return_value = SimpleNamespace(
        output_text=json.dumps(_valid_payload())
    )
    provider = MicrosoftFoundryProvider(
        project_endpoint=_FOUNDRY_ENDPOINT,
        model_deployment=_FOUNDRY_DEPLOYMENT,
        openai_client=mock_openai,
    )

    result = provider.analyze(make_request("Please review the weekly status report."))

    assert result.provider == "microsoft_foundry"
    requested = _events_named(log_events, "microsoft_foundry_analysis_requested")[-1]
    completed = _events_named(log_events, "microsoft_foundry_analysis_completed")[-1]
    assert requested["provider"] == "microsoft_foundry"
    assert requested["deployment"] == _FOUNDRY_DEPLOYMENT
    assert completed["provider"] == "microsoft_foundry"
    assert completed["duration_ms"] >= 0
    mock_openai.responses.create.assert_called_once()


def test_foundry_provider_emits_failed_event(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Foundry failures should log error_class and re-raise the original exception."""
    mock_openai = MagicMock()
    mock_openai.responses.create.side_effect = RuntimeError(_PRIVATE_ERROR)
    provider = MicrosoftFoundryProvider(
        project_endpoint=_FOUNDRY_ENDPOINT,
        model_deployment=_FOUNDRY_DEPLOYMENT,
        openai_client=mock_openai,
    )

    with pytest.raises(RuntimeError, match=_PRIVATE_ERROR):
        provider.analyze(make_request("Please review the weekly status report."))

    failed = _events_named(log_events, "microsoft_foundry_analysis_failed")[-1]
    assert failed["provider"] == "microsoft_foundry"
    assert failed["deployment"] == _FOUNDRY_DEPLOYMENT
    assert failed["error_class"] == "RuntimeError"
    assert failed["duration_ms"] >= 0
    assert _PRIVATE_ERROR not in repr(failed)


def test_foundry_malformed_output_uses_analysis_output_error_class(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Malformed Foundry JSON should fail as AnalysisOutputError."""
    mock_openai = MagicMock()
    mock_openai.responses.create.return_value = SimpleNamespace(output_text="{not-json")
    provider = MicrosoftFoundryProvider(
        project_endpoint=_FOUNDRY_ENDPOINT,
        model_deployment=_FOUNDRY_DEPLOYMENT,
        openai_client=mock_openai,
    )

    with pytest.raises(AnalysisOutputError):
        provider.analyze(make_request("Please review the weekly status report."))

    failed = _events_named(log_events, "microsoft_foundry_analysis_failed")[-1]
    assert failed["error_class"] == "AnalysisOutputError"


def test_bedrock_provider_emits_requested_and_completed_events(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Bedrock success should emit requested and completed events without network I/O."""
    mock_client = MagicMock()
    mock_client.converse.return_value = {
        "output": {"message": {"content": [{"text": json.dumps(_valid_payload())}]}}
    }
    provider = AmazonBedrockProvider(
        region=_BEDROCK_REGION,
        model_id=_BEDROCK_MODEL_ID,
        bedrock_runtime_client=mock_client,
    )

    result = provider.analyze(make_request("Please review the weekly status report."))

    assert result.provider == "amazon_bedrock"
    requested = _events_named(log_events, "amazon_bedrock_analysis_requested")[-1]
    completed = _events_named(log_events, "amazon_bedrock_analysis_completed")[-1]
    assert requested["provider"] == "amazon_bedrock"
    assert requested["model_id"] == _BEDROCK_MODEL_ID
    assert requested["region"] == _BEDROCK_REGION
    assert completed["duration_ms"] >= 0
    mock_client.converse.assert_called_once()


def test_bedrock_provider_emits_failed_event(
    make_request: RequestFactory,
    log_events: list[dict],
) -> None:
    """Bedrock failures should log error_class and re-raise the original exception."""
    mock_client = MagicMock()
    mock_client.converse.side_effect = RuntimeError(_PRIVATE_ERROR)
    provider = AmazonBedrockProvider(
        region=_BEDROCK_REGION,
        model_id=_BEDROCK_MODEL_ID,
        bedrock_runtime_client=mock_client,
    )

    with pytest.raises(RuntimeError, match=_PRIVATE_ERROR):
        provider.analyze(make_request("Please review the weekly status report."))

    failed = _events_named(log_events, "amazon_bedrock_analysis_failed")[-1]
    assert failed["provider"] == "amazon_bedrock"
    assert failed["model_id"] == _BEDROCK_MODEL_ID
    assert failed["region"] == _BEDROCK_REGION
    assert failed["error_class"] == "RuntimeError"
    assert failed["duration_ms"] >= 0
    assert _PRIVATE_ERROR not in repr(failed)
