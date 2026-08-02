"""Unit tests for domain enumerations."""

import pytest

from app.domain.enums import MessageCategory, PriorityLevel, SourceType


def test_source_type_includes_email_and_future_channels() -> None:
    """SourceType should cover the MVP channel and future extensibility points."""
    assert SourceType.EMAIL == "email"
    assert SourceType.TEAMS == "teams"
    assert SourceType.SLACK == "slack"
    assert {member.value for member in SourceType} >= {
        "email",
        "teams",
        "slack",
        "whatsapp",
        "crm",
        "erp",
        "document",
        "calendar",
        "other",
    }


def test_priority_level_values() -> None:
    """PriorityLevel should expose the supported business priorities."""
    assert list(PriorityLevel) == [
        PriorityLevel.LOW,
        PriorityLevel.MEDIUM,
        PriorityLevel.HIGH,
        PriorityLevel.CRITICAL,
    ]


def test_message_category_values() -> None:
    """MessageCategory should expose supported communication categories."""
    assert MessageCategory.REQUEST == "request"
    assert MessageCategory.INCIDENT.value == "incident"
    assert "approval" in MessageCategory


@pytest.mark.parametrize(
    ("enum_cls", "invalid_value"),
    [
        (SourceType, "fax"),
        (PriorityLevel, "urgent"),
        (MessageCategory, "spam"),
    ],
)
def test_invalid_enum_values_raise(enum_cls: type, invalid_value: str) -> None:
    """Unknown enum values must be rejected."""
    with pytest.raises(ValueError):
        enum_cls(invalid_value)


def test_enums_are_string_compatible() -> None:
    """StrEnum members should compare equal to their string values."""
    assert SourceType("email") is SourceType.EMAIL
    assert PriorityLevel("high") is PriorityLevel.HIGH
    assert MessageCategory("inquiry") is MessageCategory.INQUIRY
