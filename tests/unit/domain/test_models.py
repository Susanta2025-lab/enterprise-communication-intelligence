"""Unit tests for communication domain models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.enums import MessageCategory, PriorityLevel, SourceType
from app.domain.models import (
    ActionItem,
    CommunicationAnalysis,
    CommunicationMessage,
    DraftReply,
    MessageMetadata,
    Priority,
    Summary,
)


def _valid_metadata(**overrides: object) -> MessageMetadata:
    payload: dict[str, object] = {
        "source_type": SourceType.EMAIL,
        "sender": "alice@example.com",
        "recipients": ["bob@example.com"],
        "subject": "Quarterly report",
    }
    payload.update(overrides)
    return MessageMetadata.model_validate(payload)


def test_communication_message_accepts_valid_payload() -> None:
    """Valid messages with required metadata should construct successfully."""
    message = CommunicationMessage(
        body="Please review the attached quarterly report.",
        metadata=_valid_metadata(),
        message_id="msg-001",
    )

    assert message.body.startswith("Please review")
    assert message.metadata.source_type is SourceType.EMAIL
    assert message.metadata.sender == "alice@example.com"
    assert message.message_id == "msg-001"


def test_empty_message_body_is_rejected() -> None:
    """Blank communication bodies must fail validation."""
    with pytest.raises(ValidationError) as exc_info:
        CommunicationMessage(body="   ", metadata=_valid_metadata())

    assert "body must not be empty" in str(exc_info.value)


def test_missing_metadata_is_rejected() -> None:
    """CommunicationMessage requires metadata."""
    with pytest.raises(ValidationError):
        CommunicationMessage.model_validate({"body": "Hello"})


def test_missing_sender_is_rejected() -> None:
    """Sender is required metadata."""
    with pytest.raises(ValidationError):
        MessageMetadata.model_validate({"source_type": SourceType.EMAIL})


def test_invalid_source_type_is_rejected() -> None:
    """Unknown source types must fail validation."""
    with pytest.raises(ValidationError):
        MessageMetadata.model_validate(
            {
                "source_type": "carrier-pigeon",
                "sender": "alice@example.com",
            }
        )


def test_invalid_priority_level_is_rejected() -> None:
    """Unknown priority levels must fail validation."""
    with pytest.raises(ValidationError):
        Priority.model_validate({"level": "super-high"})


def test_summary_confidence_bounds() -> None:
    """Summary confidence must stay within 0.0-1.0."""
    with pytest.raises(ValidationError):
        Summary(text="Short summary", confidence=1.5)


def test_communication_analysis_model() -> None:
    """CommunicationAnalysis should compose nested domain objects."""
    analysis = CommunicationAnalysis(
        message_id="msg-001",
        summary=Summary(text="Review requested for quarterly report.", confidence=0.91),
        priority=Priority(
            level=PriorityLevel.HIGH,
            rationale="Explicit review request with deadline language.",
            confidence=0.88,
        ),
        category=MessageCategory.REQUEST,
        action_items=[
            ActionItem(
                description="Review quarterly report",
                owner="bob@example.com",
                due_at=datetime(2026, 8, 10, tzinfo=UTC),
                priority=PriorityLevel.HIGH,
            )
        ],
        draft_reply=DraftReply(
            body="Thanks, I will review the report and respond by Friday.",
            tone="professional",
            confidence=0.8,
        ),
    )

    assert analysis.priority.level is PriorityLevel.HIGH
    assert analysis.category is MessageCategory.REQUEST
    assert len(analysis.action_items) == 1
    assert analysis.draft_reply is not None
    assert analysis.draft_reply.tone == "professional"


def test_action_item_empty_description_rejected() -> None:
    """Action items require a non-empty description."""
    with pytest.raises(ValidationError):
        ActionItem(description="")


def test_draft_reply_empty_body_rejected() -> None:
    """Draft replies require a non-empty body."""
    with pytest.raises(ValidationError):
        DraftReply(body=" ")


def test_model_serialization_and_deserialization() -> None:
    """Domain models should round-trip through JSON serialization."""
    message = CommunicationMessage(
        body="Can we schedule a follow-up?",
        metadata=_valid_metadata(
            source_type=SourceType.TEAMS,
            subject="Follow-up",
            thread_id="thread-42",
            sent_at=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
        ),
    )

    payload = message.model_dump(mode="json")
    restored = CommunicationMessage.model_validate(payload)

    assert restored == message
    assert restored.metadata.source_type is SourceType.TEAMS
    assert restored.model_dump_json()


def test_future_channel_source_types_are_supported() -> None:
    """Non-email channels should be first-class SourceType values."""
    for source_type in (SourceType.SLACK, SourceType.WHATSAPP, SourceType.CRM):
        metadata = _valid_metadata(source_type=source_type, subject=None)
        message = CommunicationMessage(body="Channel-neutral body", metadata=metadata)
        assert message.metadata.source_type is source_type
