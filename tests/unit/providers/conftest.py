"""Shared fixtures for provider unit tests."""

from collections.abc import Callable

import pytest

from app.domain.enums import SourceType
from app.domain.models import CommunicationMessage, MessageMetadata
from app.domain.schemas import CommunicationRequest

RequestFactory = Callable[..., CommunicationRequest]


@pytest.fixture
def make_request() -> RequestFactory:
    """Return a helper that builds valid CommunicationRequest objects."""

    def _make_request(
        body: str,
        *,
        subject: str | None = "Status update",
        sender: str = "alice@example.com",
        recipients: list[str] | None = None,
        message_id: str | None = "msg-001",
        include_draft_reply: bool = True,
        include_action_items: bool = True,
    ) -> CommunicationRequest:
        return CommunicationRequest(
            message=CommunicationMessage(
                body=body,
                message_id=message_id,
                metadata=MessageMetadata(
                    source_type=SourceType.EMAIL,
                    sender=sender,
                    recipients=recipients or ["bob@example.com"],
                    subject=subject,
                ),
            ),
            include_draft_reply=include_draft_reply,
            include_action_items=include_action_items,
        )

    return _make_request
