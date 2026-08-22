"""Unit tests for provider-neutral communication capabilities."""

import pytest

from app.domain.enums import CommunicationCapability
from app.domain.models.capabilities import (
    normalize_communication_capabilities,
    parse_stored_communication_capabilities,
    require_requested_communication_capabilities,
    serialize_communication_capabilities,
)


def test_allowed_capability_values() -> None:
    """The domain model exposes mail.read and mail.send only."""
    assert list(CommunicationCapability) == [
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    ]
    assert CommunicationCapability.MAIL_READ == "mail.read"
    assert CommunicationCapability.MAIL_SEND == "mail.send"


def test_none_remains_unknown_legacy_metadata() -> None:
    """NULL capability metadata stays None rather than an invented grant."""
    assert normalize_communication_capabilities(None) is None
    assert serialize_communication_capabilities(None) is None
    assert parse_stored_communication_capabilities(None) is None


def test_empty_list_is_explicit_empty_grant() -> None:
    """An empty list is authoritative 'no mail capability'."""
    assert normalize_communication_capabilities(()) == ()
    assert serialize_communication_capabilities(()) == []
    assert parse_stored_communication_capabilities([]) == ()


def test_valid_read_send_and_both_are_normalized() -> None:
    """Known capabilities serialize in stable enum order."""
    assert normalize_communication_capabilities(
        [CommunicationCapability.MAIL_READ]
    ) == (CommunicationCapability.MAIL_READ,)
    assert normalize_communication_capabilities(
        [CommunicationCapability.MAIL_SEND]
    ) == (CommunicationCapability.MAIL_SEND,)
    assert normalize_communication_capabilities(
        [CommunicationCapability.MAIL_SEND, CommunicationCapability.MAIL_READ]
    ) == (CommunicationCapability.MAIL_READ, CommunicationCapability.MAIL_SEND)
    assert serialize_communication_capabilities(
        (CommunicationCapability.MAIL_SEND, CommunicationCapability.MAIL_READ)
    ) == ["mail.read", "mail.send"]


def test_duplicates_are_normalized() -> None:
    """Duplicate values collapse to a unique stable tuple."""
    assert normalize_communication_capabilities(
        ["mail.read", "mail.read", "mail.send"]
    ) == (CommunicationCapability.MAIL_READ, CommunicationCapability.MAIL_SEND)


def test_unknown_capability_is_rejected() -> None:
    """Raw Google/Microsoft scope strings are not domain capabilities."""
    with pytest.raises(ValueError):
        normalize_communication_capabilities(["https://mail.google.com/"])
    with pytest.raises(ValueError):
        normalize_communication_capabilities(["Mail.Send"])
    with pytest.raises(ValueError):
        parse_stored_communication_capabilities(["mail.write"])


def test_requested_capabilities_must_be_explicit() -> None:
    """Authorization sessions cannot store unknown/NULL requested grants."""
    required = require_requested_communication_capabilities(
        [CommunicationCapability.MAIL_READ, CommunicationCapability.MAIL_SEND]
    )
    assert required == (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    )
