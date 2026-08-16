"""Unit tests for shared LLM analysis output parsing and mapping."""

import json
from datetime import datetime
from typing import Any

import pytest

from app.domain.enums import MessageCategory, PriorityLevel
from app.providers.common.output import (
    AnalysisOutput,
    AnalysisOutputError,
    parse_analysis_output,
    to_communication_analysis,
)
from tests.unit.providers.conftest import RequestFactory


def _valid_payload(**overrides: Any) -> dict[str, Any]:
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


def test_parse_analysis_output_accepts_valid_json() -> None:
    """Valid JSON should parse into AnalysisOutput."""
    output = parse_analysis_output(json.dumps(_valid_payload()))

    assert isinstance(output, AnalysisOutput)
    assert output.summary_text == "The sender asked Bob to review the weekly status report."
    assert output.priority_level is PriorityLevel.HIGH
    assert output.category is MessageCategory.REQUEST
    assert len(output.action_items) == 1
    assert output.draft_reply is not None


@pytest.mark.parametrize("output_text", ["", "   ", "\n\t"])
def test_parse_analysis_output_rejects_empty_text(output_text: str) -> None:
    """Empty or whitespace-only output must be rejected."""
    with pytest.raises(AnalysisOutputError, match="empty analysis response"):
        parse_analysis_output(output_text)


def test_parse_analysis_output_rejects_malformed_json() -> None:
    """Non-JSON text must be rejected."""
    with pytest.raises(AnalysisOutputError, match="malformed JSON"):
        parse_analysis_output("not-json")


@pytest.mark.parametrize(
    "payload",
    [
        {"summary_text": "Missing the rest of the schema."},
        _valid_payload(priority_level="urgent"),
        _valid_payload(category="email"),
        _valid_payload(action_items=[{"description": "x"}]),
        {**_valid_payload(), "unexpected_field": "not allowed"},
    ],
)
def test_parse_analysis_output_rejects_schema_invalid_json(payload: dict[str, Any]) -> None:
    """JSON that does not match the analysis schema must be rejected."""
    with pytest.raises(AnalysisOutputError, match="does not match the analysis schema"):
        parse_analysis_output(json.dumps(payload))


def test_out_of_range_confidence_fails_domain_mapping(
    make_request: RequestFactory,
) -> None:
    """Confidence bounds are enforced by domain models during mapping."""
    output = parse_analysis_output(json.dumps(_valid_payload(summary_confidence=1.5)))

    with pytest.raises(AnalysisOutputError, match="failed domain validation"):
        to_communication_analysis(output, make_request("Please review this."))


def test_to_communication_analysis_maps_domain_fields(
    make_request: RequestFactory,
) -> None:
    """Validated output should map onto existing domain analysis models."""
    output = parse_analysis_output(json.dumps(_valid_payload()))
    request = make_request("Please review the weekly status report.")
    analysis = to_communication_analysis(output, request)

    assert analysis.message_id == "msg-001"
    assert analysis.summary.text == "The sender asked Bob to review the weekly status report."
    assert analysis.summary.confidence == 0.9
    assert analysis.priority.level is PriorityLevel.HIGH
    assert analysis.priority.rationale == "The message requests a timely review."
    assert analysis.priority.confidence == 0.8
    assert analysis.category is MessageCategory.REQUEST
    assert len(analysis.action_items) == 1
    assert analysis.action_items[0].description == "Review the weekly status report"
    assert analysis.action_items[0].owner == "bob@example.com"
    assert analysis.action_items[0].due_at == datetime.fromisoformat("2026-08-14T17:00:00")
    assert analysis.action_items[0].priority is PriorityLevel.HIGH
    assert analysis.draft_reply is not None
    assert analysis.draft_reply.body.startswith("Thank you.")
    assert analysis.draft_reply.tone == "neutral"
    assert analysis.draft_reply.confidence == 0.85


def test_include_action_items_false_drops_model_action_items(
    make_request: RequestFactory,
) -> None:
    """Request flags must omit action items even when the model supplied them."""
    output = parse_analysis_output(json.dumps(_valid_payload()))
    request = make_request(
        "Please review the weekly status report.",
        include_action_items=False,
    )
    analysis = to_communication_analysis(output, request)

    assert output.action_items
    assert analysis.action_items == []


def test_include_draft_reply_false_drops_model_draft_reply(
    make_request: RequestFactory,
) -> None:
    """Request flags must omit draft replies even when the model supplied one."""
    output = parse_analysis_output(json.dumps(_valid_payload()))
    request = make_request(
        "Please review the weekly status report.",
        include_draft_reply=False,
    )
    analysis = to_communication_analysis(output, request)

    assert output.draft_reply is not None
    assert analysis.draft_reply is None


def test_optional_due_at_none_is_preserved(make_request: RequestFactory) -> None:
    """A null action-item due date should map to None."""
    output = parse_analysis_output(
        json.dumps(
            _valid_payload(
                action_items=[
                    {
                        "description": "Review the weekly status report",
                        "owner": "bob@example.com",
                        "due_at": None,
                        "priority": "high",
                    }
                ]
            )
        )
    )
    analysis = to_communication_analysis(output, make_request("Please review this."))

    assert analysis.action_items[0].due_at is None


def test_invalid_due_at_raises_analysis_output_error() -> None:
    """An invalid action-item due date must be rejected during output validation."""
    with pytest.raises(AnalysisOutputError):
        parse_analysis_output(
            json.dumps(
                _valid_payload(
                    action_items=[
                        {
                            "description": "Review the weekly status report",
                            "owner": None,
                            "due_at": "not-a-date",
                            "priority": None,
                        }
                    ]
                )
            )
        )


def test_valid_due_at_is_parsed_as_datetime() -> None:
    """A valid ISO-8601 action-item due date must be parsed as a datetime."""
    output = parse_analysis_output(
        json.dumps(
            _valid_payload(
                action_items=[
                    {
                        "description": "Review the weekly status report",
                        "owner": None,
                        "due_at": "2026-08-21T17:00:00+01:00",
                        "priority": None,
                    }
                ]
            )
        )
    )

    assert isinstance(output.action_items[0].due_at, datetime)
    assert output.action_items[0].due_at.isoformat() == "2026-08-21T17:00:00+01:00"
