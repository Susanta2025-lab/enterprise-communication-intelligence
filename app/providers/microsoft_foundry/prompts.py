"""Prompt construction for the Microsoft Foundry provider."""

from app.domain.schemas import CommunicationRequest

SYSTEM_PROMPT = """You analyze a single business communication.
Operate only on the supplied content. Do not fabricate facts, people, dates, or commitments.
Summarize the communication, classify its priority, and classify its category.
Extract action items only when the request says they are required; otherwise return an empty list.
Generate a draft reply only when the request says it is required; otherwise return null.
Priority must be one of: low, medium, high, critical.
Category must be one of: general, request, incident, approval, notification, inquiry, other.
"""


def build_user_prompt(request: CommunicationRequest) -> str:
    """Build a deterministic user prompt from the communication request."""
    message = request.message
    metadata = message.metadata
    recipients = ", ".join(metadata.recipients) if metadata.recipients else "(none)"
    subject = metadata.subject or "(none)"
    sent_at = metadata.sent_at.isoformat() if metadata.sent_at else "(unknown)"
    action_items_required = "yes" if request.include_action_items else "no"
    draft_reply_required = "yes" if request.include_draft_reply else "no"

    return (
        "Analyze the following communication.\n"
        f"Action items required: {action_items_required}\n"
        f"Draft reply required: {draft_reply_required}\n"
        f"Source type: {metadata.source_type.value}\n"
        f"Sender: {metadata.sender}\n"
        f"Recipients: {recipients}\n"
        f"Subject: {subject}\n"
        f"Sent at: {sent_at}\n"
        "Body:\n"
        f"{message.body}"
    )
