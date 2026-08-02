"""Deterministic mock AI provider for local development and tests."""

from app.domain.enums import MessageCategory, PriorityLevel
from app.domain.interfaces import AIProvider
from app.domain.models import (
    ActionItem,
    CommunicationAnalysis,
    CommunicationMessage,
    DraftReply,
    Priority,
    Summary,
)
from app.domain.schemas import CommunicationAnalysisResult, CommunicationRequest

_URGENT_KEYWORDS = ("urgent", "asap", "immediately", "critical", "emergency")
_ACTION_KEYWORDS = (
    "meeting",
    "deadline",
    "please review",
    "action required",
    "follow up",
    "schedule",
    "by friday",
    "by tomorrow",
)
_PROMO_KEYWORDS = ("unsubscribe", "discount", "sale", "promotion", "newsletter", "offer")
_APPROVAL_KEYWORDS = ("approve", "approval", "sign off")
_INCIDENT_KEYWORDS = ("outage", "incident", "breach", "down")
_INQUIRY_KEYWORDS = ("could you", "can you", "how do", "what is", "?")
_REQUEST_KEYWORDS = ("please", "need you to", "kindly", "request")


class MockAIProvider(AIProvider):
    """Simple rule-based AI provider with stable, offline output."""

    PROVIDER_NAME = "mock"

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication using deterministic keyword heuristics."""
        message = request.message
        haystack = _combined_text(message)

        priority = _classify_priority(haystack)
        category = _classify_category(haystack)
        action_items: list[ActionItem] = []
        if request.include_action_items:
            action_items = _extract_action_items(haystack, message, priority.level)

        draft_reply: DraftReply | None = None
        if request.include_draft_reply:
            draft_reply = _build_draft_reply(priority.level)

        analysis = CommunicationAnalysis(
            message_id=message.message_id,
            summary=_build_summary(message),
            priority=priority,
            category=category,
            action_items=action_items,
            draft_reply=draft_reply,
        )
        return CommunicationAnalysisResult(
            analysis=analysis,
            provider=self.PROVIDER_NAME,
        )


def _combined_text(message: CommunicationMessage) -> str:
    """Build a lowercase search corpus from subject and body."""
    subject = message.metadata.subject or ""
    return f"{subject}\n{message.body}".lower()


def _build_summary(message: CommunicationMessage) -> Summary:
    """Create a short deterministic summary from subject or body."""
    if message.metadata.subject:
        text = f"Summary: {message.metadata.subject}"
    else:
        snippet = message.body.strip()
        if len(snippet) > 120:
            snippet = f"{snippet[:117].rstrip()}..."
        text = f"Summary: {snippet}"
    return Summary(text=text, confidence=1.0)


def _classify_priority(haystack: str) -> Priority:
    """Classify priority from simple keyword rules."""
    if any(keyword in haystack for keyword in ("critical", "emergency")):
        return Priority(
            level=PriorityLevel.CRITICAL,
            rationale="Detected critical or emergency language.",
            confidence=1.0,
        )
    if any(keyword in haystack for keyword in _URGENT_KEYWORDS):
        return Priority(
            level=PriorityLevel.HIGH,
            rationale="Detected urgent language.",
            confidence=1.0,
        )
    if any(keyword in haystack for keyword in _PROMO_KEYWORDS):
        return Priority(
            level=PriorityLevel.LOW,
            rationale="Detected promotional language.",
            confidence=1.0,
        )
    if any(keyword in haystack for keyword in _ACTION_KEYWORDS):
        return Priority(
            level=PriorityLevel.HIGH,
            rationale="Detected action-oriented language.",
            confidence=1.0,
        )
    return Priority(
        level=PriorityLevel.MEDIUM,
        rationale="No strong priority signals detected.",
        confidence=1.0,
    )


def _classify_category(haystack: str) -> MessageCategory:
    """Classify message category from simple keyword rules."""
    if any(keyword in haystack for keyword in _INCIDENT_KEYWORDS):
        return MessageCategory.INCIDENT
    if any(keyword in haystack for keyword in _APPROVAL_KEYWORDS):
        return MessageCategory.APPROVAL
    if any(keyword in haystack for keyword in _PROMO_KEYWORDS):
        return MessageCategory.NOTIFICATION
    if any(keyword in haystack for keyword in _INQUIRY_KEYWORDS):
        return MessageCategory.INQUIRY
    if any(keyword in haystack for keyword in _REQUEST_KEYWORDS):
        return MessageCategory.REQUEST
    return MessageCategory.GENERAL


def _extract_action_items(
    haystack: str,
    message: CommunicationMessage,
    priority_level: PriorityLevel,
) -> list[ActionItem]:
    """Return zero or one deterministic action item when action cues exist."""
    if not any(keyword in haystack for keyword in _ACTION_KEYWORDS):
        return []

    subject = message.metadata.subject
    description = (
        f"Follow up on: {subject}" if subject else "Follow up on the communication"
    )
    return [
        ActionItem(
            description=description,
            owner=message.metadata.recipients[0] if message.metadata.recipients else None,
            priority=priority_level,
        )
    ]


def _build_draft_reply(priority_level: PriorityLevel) -> DraftReply:
    """Return a short neutral draft reply."""
    if priority_level in {PriorityLevel.HIGH, PriorityLevel.CRITICAL}:
        body = (
            "Thank you for flagging this. I am reviewing it now and will follow up shortly."
        )
    elif priority_level is PriorityLevel.LOW:
        body = "Thank you for the update. I have noted this message."
    else:
        body = "Thank you for your message. I will review this and follow up shortly."
    return DraftReply(body=body, tone="neutral", confidence=1.0)
