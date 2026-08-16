"""Unit tests for the Amazon Bedrock AI provider."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ConfigurationError
from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult
from app.providers.amazon_bedrock.output import BEDROCK_ANALYSIS_JSON_SCHEMA
from app.providers.amazon_bedrock.provider import AmazonBedrockProvider
from app.providers.common.output import AnalysisOutput, AnalysisOutputError
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt
from tests.unit.providers.conftest import RequestFactory

_REGION = "eu-south-2"
_MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _valid_analysis_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "summary_text": "The sender asked Bob to review the weekly status report.",
        "summary_confidence": 0.9,
        "priority_level": "high",
        "priority_rationale": "The message requests a timely review.",
        "priority_confidence": 0.8,
        "category": "request",
        "action_items": [
            {
                "description": "Review the weekly status report",
                "owner": "bob@example.com",
                "due_at": "2026-08-14T17:00:00",
                "priority": "high",
            }
        ],
        "draft_reply": {
            "body": "Thank you. I will review the weekly status report and follow up.",
            "tone": "neutral",
            "confidence": 0.85,
        },
    }
    payload.update(overrides)
    return payload


def _converse_response(payload: dict[str, Any] | str) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"output": {"message": {"content": [{"text": text}]}}}


def _provider_with_output(
    payload: dict[str, Any] | str,
    *,
    error: Exception | None = None,
) -> tuple[AmazonBedrockProvider, MagicMock]:
    mock_client = MagicMock()
    if error is not None:
        mock_client.converse.side_effect = error
    else:
        mock_client.converse.return_value = _converse_response(payload)

    provider = AmazonBedrockProvider(
        region=_REGION,
        model_id=_MODEL_ID,
        bedrock_runtime_client=mock_client,
    )
    return provider, mock_client


def test_amazon_bedrock_provider_conforms_to_ai_provider_interface() -> None:
    """AmazonBedrockProvider must implement the domain AIProvider contract."""
    provider, _ = _provider_with_output(_valid_analysis_payload())
    assert isinstance(provider, AIProvider)


def test_constructor_accepts_valid_region_and_model_id() -> None:
    """Valid region and model ID should be stored without creating a client."""
    provider = AmazonBedrockProvider(region=_REGION, model_id=_MODEL_ID)

    assert provider._region == _REGION
    assert provider._model_id == _MODEL_ID
    assert provider._bedrock_runtime_client is None


@pytest.mark.parametrize(
    ("region", "model_id"),
    [
        ("   ", _MODEL_ID),
        ("", _MODEL_ID),
        (_REGION, "   "),
        (_REGION, ""),
        ("   ", "   "),
    ],
)
def test_constructor_rejects_blank_region_or_model_id(region: str, model_id: str) -> None:
    """Blank region or model ID must fail before any SDK call."""
    with pytest.raises(ConfigurationError) as exc_info:
        AmazonBedrockProvider(region=region, model_id=model_id)

    assert "BEDROCK_REGION" in exc_info.value.message
    assert "BEDROCK_MODEL_ID" in exc_info.value.message


def test_analyze_uses_injected_runtime_client(
    make_request: RequestFactory,
) -> None:
    """An injected client must be used instead of boto3.client."""
    provider, mock_client = _provider_with_output(_valid_analysis_payload())

    with patch("app.providers.amazon_bedrock.provider.boto3.client") as mock_boto_client:
        result = provider.analyze(make_request("Please review the weekly status report."))

    mock_boto_client.assert_not_called()
    mock_client.converse.assert_called_once()
    assert result.provider == "amazon_bedrock"


@patch("app.providers.amazon_bedrock.provider.boto3.client")
def test_lazy_client_creation_reuses_runtime_client(
    mock_boto_client: MagicMock,
    make_request: RequestFactory,
) -> None:
    """Uninjected clients should be created lazily and reused without a profile."""
    mock_runtime = MagicMock()
    mock_runtime.converse.return_value = _converse_response(_valid_analysis_payload())
    mock_boto_client.return_value = mock_runtime

    provider = AmazonBedrockProvider(region=_REGION, model_id=_MODEL_ID)
    mock_boto_client.assert_not_called()

    first = provider.analyze(make_request("Please review this."))
    second = provider.analyze(make_request("Please review this again."))

    mock_boto_client.assert_called_once_with(
        "bedrock-runtime",
        region_name=_REGION,
    )
    kwargs = mock_boto_client.call_args.kwargs
    assert "profile_name" not in kwargs
    assert "aws_access_key_id" not in kwargs
    assert "aws_secret_access_key" not in kwargs
    assert "aws_session_token" not in kwargs
    assert first.provider == "amazon_bedrock"
    assert second.provider == "amazon_bedrock"
    assert mock_runtime.converse.call_count == 2


def test_converse_request_uses_configured_model_and_shared_prompts(
    make_request: RequestFactory,
) -> None:
    """Converse must use the configured model ID and shared ECI prompts."""
    request = make_request("Please review the weekly status report.")
    provider, mock_client = _provider_with_output(_valid_analysis_payload())
    provider.analyze(request)

    kwargs = mock_client.converse.call_args.kwargs
    assert kwargs["modelId"] == _MODEL_ID
    assert kwargs["system"] == [{"text": SYSTEM_PROMPT}]
    assert kwargs["messages"] == [
        {
            "role": "user",
            "content": [{"text": build_user_prompt(request)}],
        }
    ]


def test_converse_request_uses_json_schema_structured_output(
    make_request: RequestFactory,
) -> None:
    """Converse outputConfig must request JSON Schema structured output as a string."""
    provider, mock_client = _provider_with_output(_valid_analysis_payload())
    provider.analyze(make_request("Please review the weekly status report."))

    kwargs = mock_client.converse.call_args.kwargs
    text_format = kwargs["outputConfig"]["textFormat"]
    json_schema = text_format["structure"]["jsonSchema"]
    schema_payload = json.loads(json_schema["schema"])

    assert text_format["type"] == "json_schema"
    assert json_schema["name"] == "communication_analysis"
    assert isinstance(json_schema["schema"], str)
    assert json_schema["schema"] == BEDROCK_ANALYSIS_JSON_SCHEMA
    assert schema_payload == AnalysisOutput.model_json_schema()


def test_successful_analysis_maps_domain_result(make_request: RequestFactory) -> None:
    """A valid Converse response should map onto CommunicationAnalysisResult."""
    provider, _ = _provider_with_output(_valid_analysis_payload())
    result = provider.analyze(make_request("Please review the weekly status report."))

    assert isinstance(result, CommunicationAnalysisResult)
    assert result.provider == AmazonBedrockProvider.PROVIDER_NAME
    assert result.provider == "amazon_bedrock"
    assert result.analysis.message_id == "msg-001"
    assert result.analysis.summary.text == (
        "The sender asked Bob to review the weekly status report."
    )
    assert result.analysis.priority.level is PriorityLevel.HIGH
    assert result.analysis.category is MessageCategory.REQUEST
    assert len(result.analysis.action_items) == 1
    assert result.analysis.draft_reply is not None


def test_action_items_disabled(make_request: RequestFactory) -> None:
    """Action items must be omitted when the request disables them."""
    provider, _ = _provider_with_output(_valid_analysis_payload())
    result = provider.analyze(
        make_request("Please review the weekly status report.", include_action_items=False)
    )

    assert result.analysis.action_items == []


def test_draft_reply_disabled(make_request: RequestFactory) -> None:
    """Draft replies must be omitted when the request disables them."""
    provider, _ = _provider_with_output(_valid_analysis_payload())
    result = provider.analyze(
        make_request("Please review the weekly status report.", include_draft_reply=False)
    )

    assert result.analysis.draft_reply is None


@pytest.mark.parametrize(
    "output_text",
    [
        "not-json",
        json.dumps({"summary_text": "Missing the rest of the schema."}),
    ],
)
def test_malformed_model_output_raises_analysis_output_error(
    make_request: RequestFactory,
    output_text: str,
) -> None:
    """Malformed or schema-invalid model JSON must surface as AnalysisOutputError."""
    provider, _ = _provider_with_output(output_text)

    with pytest.raises(AnalysisOutputError):
        provider.analyze(make_request("Please review this."))


def test_sdk_failure_propagates(make_request: RequestFactory) -> None:
    """SDK failures must propagate without an invented Bedrock exception hierarchy."""
    provider, _ = _provider_with_output(
        _valid_analysis_payload(),
        error=RuntimeError("bedrock unreachable"),
    )

    with pytest.raises(RuntimeError, match="bedrock unreachable"):
        provider.analyze(make_request("Please review this."))
