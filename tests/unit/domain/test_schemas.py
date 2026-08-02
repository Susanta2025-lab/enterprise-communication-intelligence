"""Unit tests for domain input and output schemas."""

import pytest
from pydantic import ValidationError

from app.domain.enums import MessageCategory, PriorityLevel, SourceType
from app.domain.models import (
    CommunicationAnalysis,
    CommunicationMessage,
    MessageMetadata,
    Priority,
    Summary,
)
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest


def _sample_message() -> CommunicationMessage:
    return CommunicationMessage(
        body="Please approve the purchase order.",
        metadata=MessageMetadata(
            source_type=SourceType.EMAIL,
            sender="finance@example.com",
            recipients=["manager@example.com"],
            subject="PO approval",
        ),
        message_id="msg-100",
    )


def _sample_analysis() -> CommunicationAnalysis:
    return CommunicationAnalysis(
        message_id="msg-100",
        summary=Summary(text="Purchase order approval requested."),
        priority=Priority(level=PriorityLevel.MEDIUM),
        category=MessageCategory.APPROVAL,
    )


def test_communication_request_defaults() -> None:
    """CommunicationRequest should default analysis options to enabled."""
    request = CommunicationRequest(message=_sample_message())

    assert request.include_draft_reply is True
    assert request.include_action_items is True
    assert request.message.metadata.source_type is SourceType.EMAIL


def test_communication_request_rejects_empty_message_body() -> None:
    """Invalid nested messages must fail request validation."""
    with pytest.raises(ValidationError):
        CommunicationRequest.model_validate(
            {
                "message": {
                    "body": "",
                    "metadata": {
                        "source_type": "email",
                        "sender": "alice@example.com",
                    },
                }
            }
        )


def test_communication_request_rejects_invalid_source_type() -> None:
    """Invalid source types must fail request validation."""
    with pytest.raises(ValidationError):
        CommunicationRequest.model_validate(
            {
                "message": {
                    "body": "Hello",
                    "metadata": {
                        "source_type": "unknown-channel",
                        "sender": "alice@example.com",
                    },
                }
            }
        )


def test_communication_analysis_result_serialization_round_trip() -> None:
    """Analysis results should serialize and deserialize cleanly."""
    result = CommunicationAnalysisResult(
        analysis=_sample_analysis(),
        provider="mock",
    )

    payload = result.model_dump(mode="json")
    restored = CommunicationAnalysisResult.model_validate(payload)

    assert restored == result
    assert restored.provider == "mock"
    assert restored.analysis.category is MessageCategory.APPROVAL
    assert '"priority":{"level":"medium"' in result.model_dump_json()


def test_communication_analysis_result_requires_analysis() -> None:
    """Analysis payload is required on the result schema."""
    with pytest.raises(ValidationError):
        CommunicationAnalysisResult.model_validate({})
