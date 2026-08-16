"""Unit tests for the Microsoft Foundry AI provider."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ConfigurationError
from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult
from app.providers.common.output import AnalysisOutputError
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt
from app.providers.microsoft_foundry.output import FOUNDRY_ANALYSIS_JSON_SCHEMA
from app.providers.microsoft_foundry.provider import MicrosoftFoundryProvider
from tests.unit.providers.conftest import RequestFactory

_PROJECT_ENDPOINT = "https://eci-foundry-dev-susanta.services.ai.azure.com/api/projects/eci-project-dev"
_MODEL_DEPLOYMENT = "eci-gpt-54-mini"


def _valid_foundry_payload(**overrides: Any) -> dict[str, Any]:
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


def _provider_with_output(
    payload: dict[str, Any] | str,
    *,
    error: Exception | None = None,
) -> tuple[MicrosoftFoundryProvider, MagicMock]:
    mock_openai = MagicMock()
    if error is not None:
        mock_openai.responses.create.side_effect = error
    else:
        output_text = payload if isinstance(payload, str) else json.dumps(payload)
        mock_openai.responses.create.return_value = SimpleNamespace(output_text=output_text)

    provider = MicrosoftFoundryProvider(
        project_endpoint=_PROJECT_ENDPOINT,
        model_deployment=_MODEL_DEPLOYMENT,
        openai_client=mock_openai,
    )
    return provider, mock_openai


def test_microsoft_foundry_provider_conforms_to_ai_provider_interface() -> None:
    """MicrosoftFoundryProvider must implement the domain AIProvider contract."""
    provider, _ = _provider_with_output(_valid_foundry_payload())
    assert isinstance(provider, AIProvider)


def test_successful_analysis_maps_domain_result(make_request: RequestFactory) -> None:
    """A valid Foundry response should map onto CommunicationAnalysisResult."""
    provider, _ = _provider_with_output(_valid_foundry_payload())
    result = provider.analyze(make_request("Please review the weekly status report."))

    assert isinstance(result, CommunicationAnalysisResult)
    assert result.provider == "microsoft_foundry"
    assert result.analysis.summary.text == (
        "The sender asked Bob to review the weekly status report."
    )
    assert result.analysis.summary.confidence == 0.9
    assert result.analysis.priority.level is PriorityLevel.HIGH
    assert result.analysis.priority.rationale == "The message requests a timely review."
    assert result.analysis.category is MessageCategory.REQUEST
    assert result.analysis.message_id == "msg-001"


def test_uses_configured_deployment_name(make_request: RequestFactory) -> None:
    """The Responses API call must use the configured deployment name."""
    provider, mock_openai = _provider_with_output(_valid_foundry_payload())
    provider.analyze(make_request("Please review the weekly status report."))

    kwargs = mock_openai.responses.create.call_args.kwargs
    assert kwargs["model"] == _MODEL_DEPLOYMENT
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["name"] == "communication_analysis"
    assert kwargs["text"]["format"]["schema"] == FOUNDRY_ANALYSIS_JSON_SCHEMA
    assert "api_key" not in kwargs


def test_responses_create_uses_instructions_and_string_input(
    make_request: RequestFactory,
) -> None:
    """Foundry calls must use top-level instructions and a string user prompt."""
    request = make_request("Please review the weekly status report.")
    provider, mock_openai = _provider_with_output(_valid_foundry_payload())
    provider.analyze(request)

    kwargs = mock_openai.responses.create.call_args.kwargs
    assert kwargs["instructions"] == SYSTEM_PROMPT
    assert kwargs["input"] == build_user_prompt(request)
    assert isinstance(kwargs["input"], str)
    assert kwargs["input"] != ""
    assert not isinstance(kwargs["input"], list)
    assert "role" not in kwargs
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["name"] == "communication_analysis"
    assert kwargs["text"]["format"]["schema"] == FOUNDRY_ANALYSIS_JSON_SCHEMA


def test_summary_mapping(make_request: RequestFactory) -> None:
    """Summary text and confidence should be copied from the model output."""
    provider, _ = _provider_with_output(
        _valid_foundry_payload(summary_text="Short summary.", summary_confidence=0.42)
    )
    result = provider.analyze(make_request("Status update."))

    assert result.analysis.summary.text == "Short summary."
    assert result.analysis.summary.confidence == 0.42


@pytest.mark.parametrize(
    ("priority_level", "expected"),
    [
        ("low", PriorityLevel.LOW),
        ("medium", PriorityLevel.MEDIUM),
        ("high", PriorityLevel.HIGH),
        ("critical", PriorityLevel.CRITICAL),
    ],
)
def test_priority_mapping(
    make_request: RequestFactory,
    priority_level: str,
    expected: PriorityLevel,
) -> None:
    """Each domain priority value should map from the model output."""
    provider, _ = _provider_with_output(_valid_foundry_payload(priority_level=priority_level))
    result = provider.analyze(make_request("Please review this."))

    assert result.analysis.priority.level is expected


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("general", MessageCategory.GENERAL),
        ("request", MessageCategory.REQUEST),
        ("incident", MessageCategory.INCIDENT),
        ("approval", MessageCategory.APPROVAL),
        ("notification", MessageCategory.NOTIFICATION),
        ("inquiry", MessageCategory.INQUIRY),
        ("other", MessageCategory.OTHER),
    ],
)
def test_category_mapping(
    make_request: RequestFactory,
    category: str,
    expected: MessageCategory,
) -> None:
    """Each domain category value should map from the model output."""
    provider, _ = _provider_with_output(_valid_foundry_payload(category=category))
    result = provider.analyze(make_request("Please review this."))

    assert result.analysis.category is expected


def test_action_items_enabled(make_request: RequestFactory) -> None:
    """Requested action items should be mapped into domain models."""
    provider, _ = _provider_with_output(_valid_foundry_payload())
    result = provider.analyze(
        make_request("Please review the weekly status report.", include_action_items=True)
    )

    assert len(result.analysis.action_items) == 1
    action_item = result.analysis.action_items[0]
    assert action_item.description == "Review the weekly status report"
    assert action_item.owner == "bob@example.com"
    assert action_item.due_at is not None
    assert action_item.priority is PriorityLevel.HIGH


def test_action_items_disabled(make_request: RequestFactory) -> None:
    """Action items must be omitted when the request disables them."""
    provider, mock_openai = _provider_with_output(_valid_foundry_payload())
    result = provider.analyze(
        make_request("Please review the weekly status report.", include_action_items=False)
    )

    assert result.analysis.action_items == []
    kwargs = mock_openai.responses.create.call_args.kwargs
    assert kwargs["instructions"] == SYSTEM_PROMPT
    assert isinstance(kwargs["input"], str)
    assert "Action items required: no" in kwargs["input"]


def test_draft_reply_enabled(make_request: RequestFactory) -> None:
    """Requested draft replies should be mapped into domain models."""
    provider, _ = _provider_with_output(_valid_foundry_payload())
    result = provider.analyze(
        make_request("Please review the weekly status report.", include_draft_reply=True)
    )

    assert result.analysis.draft_reply is not None
    assert result.analysis.draft_reply.body.startswith("Thank you.")
    assert result.analysis.draft_reply.tone == "neutral"
    assert result.analysis.draft_reply.confidence == 0.85


def test_draft_reply_disabled(make_request: RequestFactory) -> None:
    """Draft replies must be omitted when the request disables them."""
    provider, mock_openai = _provider_with_output(_valid_foundry_payload())
    result = provider.analyze(
        make_request("Please review the weekly status report.", include_draft_reply=False)
    )

    assert result.analysis.draft_reply is None
    kwargs = mock_openai.responses.create.call_args.kwargs
    assert kwargs["instructions"] == SYSTEM_PROMPT
    assert isinstance(kwargs["input"], str)
    assert "Draft reply required: no" in kwargs["input"]


def test_provider_name_in_result(make_request: RequestFactory) -> None:
    """The result provider field must identify Microsoft Foundry."""
    provider, _ = _provider_with_output(_valid_foundry_payload())
    result = provider.analyze(make_request("Please review this."))

    assert result.provider == MicrosoftFoundryProvider.PROVIDER_NAME
    assert result.provider == "microsoft_foundry"


@pytest.mark.parametrize(
    "output_text",
    [
        "",
        "not-json",
        json.dumps({"summary_text": "Missing the rest of the schema."}),
        json.dumps(_valid_foundry_payload(priority_level="urgent")),
        json.dumps(_valid_foundry_payload(category="email")),
        json.dumps(_valid_foundry_payload(summary_confidence=1.5)),
        json.dumps(_valid_foundry_payload(action_items=[{"description": "x"}])),
        json.dumps(
            _valid_foundry_payload(
                action_items=[
                    {
                        "description": "Review the weekly status report",
                        "owner": None,
                        "due_at": "not-a-date",
                        "priority": None,
                    }
                ]
            )
        ),
    ],
)
def test_malformed_model_output(make_request: RequestFactory, output_text: str) -> None:
    """Malformed or schema-invalid model output must be rejected explicitly."""
    provider, _ = _provider_with_output(output_text)

    with pytest.raises(AnalysisOutputError):
        provider.analyze(make_request("Please review this."))


def test_sdk_failure_propagates(make_request: RequestFactory) -> None:
    """SDK/network failures must propagate to the application service boundary."""
    provider, _ = _provider_with_output(
        _valid_foundry_payload(),
        error=RuntimeError("foundry unreachable"),
    )

    with pytest.raises(RuntimeError, match="foundry unreachable"):
        provider.analyze(make_request("Please review this."))


def test_missing_configuration_raises() -> None:
    """The provider must reject missing Foundry connection settings."""
    with pytest.raises(ConfigurationError) as exc_info:
        MicrosoftFoundryProvider(
            project_endpoint="   ",
            model_deployment=_MODEL_DEPLOYMENT,
        )

    assert "FOUNDRY_PROJECT_ENDPOINT" in exc_info.value.message
    assert "FOUNDRY_MODEL_DEPLOYMENT" in exc_info.value.message


def test_missing_deployment_raises() -> None:
    """A blank deployment name must fail before any SDK call."""
    with pytest.raises(ConfigurationError):
        MicrosoftFoundryProvider(
            project_endpoint=_PROJECT_ENDPOINT,
            model_deployment="",
        )


@patch("app.providers.microsoft_foundry.provider.AIProjectClient")
@patch("app.providers.microsoft_foundry.provider.DefaultAzureCredential")
def test_uses_default_azure_credential_and_project_client(
    mock_credential_cls: MagicMock,
    mock_project_client_cls: MagicMock,
    make_request: RequestFactory,
) -> None:
    """Uninjected clients should follow the current Microsoft SDK pattern."""
    mock_openai = MagicMock()
    mock_openai.responses.create.return_value = SimpleNamespace(
        output_text=json.dumps(_valid_foundry_payload())
    )
    mock_project_client = MagicMock()
    mock_project_client.get_openai_client.return_value = mock_openai
    mock_project_client_cls.return_value = mock_project_client
    mock_credential = MagicMock()
    mock_credential_cls.return_value = mock_credential

    provider = MicrosoftFoundryProvider(
        project_endpoint=_PROJECT_ENDPOINT,
        model_deployment=_MODEL_DEPLOYMENT,
    )
    mock_credential_cls.assert_not_called()

    result = provider.analyze(make_request("Please review this."))

    mock_credential_cls.assert_called_once_with()
    mock_project_client_cls.assert_called_once_with(
        endpoint=_PROJECT_ENDPOINT,
        credential=mock_credential,
    )
    mock_project_client.get_openai_client.assert_called_once_with()
    assert result.provider == "microsoft_foundry"

    provider.analyze(make_request("Please review this again."))
    mock_credential_cls.assert_called_once_with()
    mock_project_client.get_openai_client.assert_called_once_with()
