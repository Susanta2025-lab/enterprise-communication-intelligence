"""Unit tests for shared LLM communication-analysis prompts."""

from datetime import datetime

from app.domain.enums import SourceType
from app.domain.models import CommunicationMessage, MessageMetadata
from app.domain.schemas import CommunicationRequest
from app.providers.common.prompts import SYSTEM_PROMPT, build_user_prompt
from tests.unit.providers.conftest import RequestFactory


def test_system_prompt_preserves_eci_business_instructions() -> None:
    """The shared system prompt must retain the current ECI analysis contract."""
    assert "Do not fabricate facts, people, dates, or commitments." in SYSTEM_PROMPT
    assert "Extract action items only when the request says they are required" in SYSTEM_PROMPT
    assert "Generate a draft reply only when the request says it is required" in SYSTEM_PROMPT
    assert "Priority must be one of: low, medium, high, critical." in SYSTEM_PROMPT
    assert (
        "Category must be one of: general, request, incident, approval, "
        "notification, inquiry, other."
    ) in SYSTEM_PROMPT


def test_build_user_prompt_includes_communication_fields(
    make_request: RequestFactory,
) -> None:
    """The user prompt should include the supplied communication fields and flags."""
    request = make_request("Please review the weekly status report.")
    prompt = build_user_prompt(request)

    assert "Action items required: yes" in prompt
    assert "Draft reply required: yes" in prompt
    assert "Source type: email" in prompt
    assert "Sender: alice@example.com" in prompt
    assert "Recipients: bob@example.com" in prompt
    assert "Subject: Status update" in prompt
    assert "Sent at: (unknown)" in prompt
    assert "Please review the weekly status report." in prompt


def test_build_user_prompt_records_disabled_optional_sections(
    make_request: RequestFactory,
) -> None:
    """Disabled request flags should appear as explicit 'no' requirements."""
    request = make_request(
        "Please review the weekly status report.",
        include_action_items=False,
        include_draft_reply=False,
    )
    prompt = build_user_prompt(request)

    assert "Action items required: no" in prompt
    assert "Draft reply required: no" in prompt


def test_build_user_prompt_includes_sent_at_and_empty_recipients() -> None:
    """Optional metadata should be rendered with the existing fallbacks."""
    sent_at = datetime.fromisoformat("2026-08-14T17:00:00")
    request = CommunicationRequest(
        message=CommunicationMessage(
            body="Please review this.",
            metadata=MessageMetadata(
                source_type=SourceType.SLACK,
                sender="ops-bot",
                recipients=[],
                subject=None,
                sent_at=sent_at,
            ),
        )
    )
    prompt = build_user_prompt(request)

    assert "Source type: slack" in prompt
    assert "Sender: ops-bot" in prompt
    assert "Recipients: (none)" in prompt
    assert "Subject: (none)" in prompt
    assert f"Sent at: {sent_at.isoformat()}" in prompt
    assert "Please review this." in prompt
