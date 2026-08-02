"""Unit tests for the deterministic mock AI provider."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.interfaces import AIProvider
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest
from app.providers.mock.provider import MockAIProvider

RequestFactory = Callable[..., CommunicationRequest]


def test_mock_provider_conforms_to_ai_provider_interface() -> None:
    """MockAIProvider must implement the domain AIProvider contract."""
    provider = MockAIProvider()
    assert isinstance(provider, AIProvider)


def test_mock_provider_returns_valid_result(make_request: RequestFactory) -> None:
    """analyze() should return a valid CommunicationAnalysisResult."""
    provider = MockAIProvider()
    result = provider.analyze(
        make_request("Please review the weekly status report when you can.")
    )

    assert isinstance(result, CommunicationAnalysisResult)
    assert result.provider == "mock"
    assert result.analysis.summary.text.startswith("Summary:")
    assert result.analysis.priority.level in PriorityLevel
    assert result.analysis.category in MessageCategory
    assert result.analysis.draft_reply is not None
    assert result.analysis.message_id == "msg-001"


def test_mock_provider_is_deterministic(make_request: RequestFactory) -> None:
    """Identical inputs must produce identical outputs."""
    provider = MockAIProvider()
    request = make_request("Please schedule a meeting before the deadline.")

    first = provider.analyze(request)
    second = provider.analyze(request)

    assert first == second
    assert first.model_dump() == second.model_dump()


def test_mock_provider_handles_normal_business_communication(
    make_request: RequestFactory,
) -> None:
    """Ordinary business text should produce a medium-priority general analysis."""
    result = MockAIProvider().analyze(
        make_request("Sharing the notes from today's standup for visibility.")
    )

    assert result.analysis.priority.level is PriorityLevel.MEDIUM
    assert result.analysis.category is MessageCategory.GENERAL
    assert result.analysis.action_items == []
    assert result.analysis.draft_reply is not None
    assert "follow up shortly" in result.analysis.draft_reply.body.lower()


def test_mock_provider_handles_urgent_language(make_request: RequestFactory) -> None:
    """Urgent keywords should raise priority."""
    result = MockAIProvider().analyze(
        make_request("This is urgent and needs attention ASAP.")
    )

    assert result.analysis.priority.level is PriorityLevel.HIGH
    assert "urgent" in (result.analysis.priority.rationale or "").lower()


def test_mock_provider_handles_critical_language(make_request: RequestFactory) -> None:
    """Critical language should map to critical priority."""
    result = MockAIProvider().analyze(
        make_request("Emergency: production outage requires immediate response.")
    )

    assert result.analysis.priority.level is PriorityLevel.CRITICAL
    assert result.analysis.category is MessageCategory.INCIDENT


def test_mock_provider_handles_action_oriented_language(
    make_request: RequestFactory,
) -> None:
    """Action-oriented language should produce an action item."""
    result = MockAIProvider().analyze(
        make_request(
            "Please review the proposal and schedule a meeting before the deadline.",
            subject="Proposal review",
        )
    )

    assert result.analysis.priority.level is PriorityLevel.HIGH
    assert len(result.analysis.action_items) == 1
    assert result.analysis.action_items[0].description == "Follow up on: Proposal review"
    assert result.analysis.action_items[0].owner == "bob@example.com"


def test_mock_provider_promotional_language_is_low_priority(
    make_request: RequestFactory,
) -> None:
    """Promotional language should classify as low-priority notification."""
    result = MockAIProvider().analyze(
        make_request(
            "Spring sale! Enjoy a discount on our newsletter offers. Unsubscribe anytime."
        )
    )

    assert result.analysis.priority.level is PriorityLevel.LOW
    assert result.analysis.category is MessageCategory.NOTIFICATION


def test_mock_provider_respects_include_flags(make_request: RequestFactory) -> None:
    """Optional analysis sections should honor request flags."""
    result = MockAIProvider().analyze(
        make_request(
            "Please review this before the deadline.",
            include_draft_reply=False,
            include_action_items=False,
        )
    )

    assert result.analysis.draft_reply is None
    assert result.analysis.action_items == []


def test_invalid_input_rejected_by_domain_validation() -> None:
    """Invalid requests must fail domain validation before provider analysis."""
    with pytest.raises(ValidationError):
        CommunicationRequest.model_validate(
            {
                "message": {
                    "body": "   ",
                    "metadata": {
                        "source_type": "email",
                        "sender": "alice@example.com",
                    },
                }
            }
        )
