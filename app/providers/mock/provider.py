"""Deterministic mock AI provider for local development and tests."""

import time
from uuid import UUID

from app.core.logging import get_logger
from app.core.telemetry import elapsed_ms, error_class
from app.domain.enums import ContextMatchStrength, MessageCategory, PriorityLevel
from app.domain.exceptions import AttachmentImageInputUnsupportedError
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
from app.domain.schemas.context_suggestion import (
    BusinessContextSuggestionItem,
    BusinessContextSuggestionRequest,
    BusinessContextSuggestionResult,
)
from app.domain.schemas.tabular_analysis import (
    TabularAnalysisRequest,
    TabularAnalysisResult,
    TabularSheetSummary,
)

logger = get_logger(__name__)

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
_MAX_SUGGESTIONS = 3


class MockAIProvider(AIProvider):
    """Simple rule-based AI provider with stable, offline output."""

    PROVIDER_NAME = "mock"

    def __init__(
        self,
        *,
        supports_image_input: bool = False,
        suggestion_result: BusinessContextSuggestionResult | None = None,
        suggestion_error: Exception | None = None,
        tabular_result: TabularAnalysisResult | None = None,
        tabular_error: Exception | None = None,
    ) -> None:
        self._supports_image_input = supports_image_input
        self._suggestion_result = suggestion_result
        self._suggestion_error = suggestion_error
        self._tabular_result = tabular_result
        self._tabular_error = tabular_error

    def supports_image_input(self) -> bool:
        """Return the explicit mock image-capability flag. Default is off."""
        return self._supports_image_input

    def analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Analyze a communication using deterministic keyword heuristics."""
        logger.info(
            "mock_analysis_requested",
            provider=self.PROVIDER_NAME,
            operation="analyze",
        )
        started_at = time.perf_counter()

        try:
            result = self._analyze(request)
        except Exception as exc:
            logger.error(
                "mock_analysis_failed",
                provider=self.PROVIDER_NAME,
                operation="analyze",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "mock_analysis_completed",
            provider=self.PROVIDER_NAME,
            operation="analyze",
            duration_ms=elapsed_ms(started_at),
        )
        return result

    def suggest_business_context(
        self,
        request: BusinessContextSuggestionRequest,
    ) -> BusinessContextSuggestionResult:
        """Suggest BusinessContext candidates using deterministic heuristics."""
        logger.info(
            "mock_context_suggestion_requested",
            provider=self.PROVIDER_NAME,
            operation="suggest_business_context",
            candidate_count=len(request.candidates),
        )
        started_at = time.perf_counter()

        try:
            if self._suggestion_error is not None:
                raise self._suggestion_error
            if self._suggestion_result is not None:
                result = self._suggestion_result.model_copy(deep=True)
                result.provider = self.PROVIDER_NAME
            else:
                result = self._suggest(request)
        except Exception as exc:
            logger.error(
                "mock_context_suggestion_failed",
                provider=self.PROVIDER_NAME,
                operation="suggest_business_context",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "mock_context_suggestion_completed",
            provider=self.PROVIDER_NAME,
            operation="suggest_business_context",
            duration_ms=elapsed_ms(started_at),
            suggestion_count=len(result.suggestions),
        )
        return result

    def analyze_tabular(
        self,
        request: TabularAnalysisRequest,
    ) -> TabularAnalysisResult:
        """Analyze a bounded workbook sample with deterministic offline heuristics."""
        logger.info(
            "mock_tabular_analysis_requested",
            provider=self.PROVIDER_NAME,
            operation="analyze_tabular",
            input_character_count=request.input_character_count,
            source_truncated=request.source_truncated,
        )
        started_at = time.perf_counter()

        try:
            if self._tabular_error is not None:
                raise self._tabular_error
            if self._tabular_result is not None:
                result = self._tabular_result.model_copy(deep=True)
                result.provider = self.PROVIDER_NAME
                if request.source_truncated:
                    result.source_truncated = True
            else:
                result = self._analyze_tabular(request)
        except Exception as exc:
            logger.error(
                "mock_tabular_analysis_failed",
                provider=self.PROVIDER_NAME,
                operation="analyze_tabular",
                duration_ms=elapsed_ms(started_at),
                error_class=error_class(exc),
            )
            raise

        logger.info(
            "mock_tabular_analysis_completed",
            provider=self.PROVIDER_NAME,
            operation="analyze_tabular",
            duration_ms=elapsed_ms(started_at),
            source_truncated=result.source_truncated,
            sheet_summary_count=len(result.sheet_summaries),
        )
        return result

    def _analyze(self, request: CommunicationRequest) -> CommunicationAnalysisResult:
        """Run the deterministic keyword analysis without telemetry."""
        if request.attachment_images and not self._supports_image_input:
            raise AttachmentImageInputUnsupportedError()

        message = request.message
        haystack = _combined_text(request)

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
            summary=_build_summary(request),
            priority=priority,
            category=category,
            action_items=action_items,
            draft_reply=draft_reply,
        )
        return CommunicationAnalysisResult(
            analysis=analysis,
            provider=self.PROVIDER_NAME,
        )

    def _suggest(
        self,
        request: BusinessContextSuggestionRequest,
    ) -> BusinessContextSuggestionResult:
        """Match candidates against analysis evidence with simple token overlap."""
        if not request.candidates:
            return BusinessContextSuggestionResult(
                suggestions=[],
                no_match_reason="No active contexts were available to compare.",
                provider=self.PROVIDER_NAME,
            )

        evidence_tokens = _tokenize(
            " ".join(
                [
                    request.evidence.summary_text,
                    request.evidence.category,
                    request.evidence.priority,
                    *request.evidence.action_item_descriptions,
                ]
            )
        )
        scored: list[tuple[int, UUID, ContextMatchStrength, str]] = []
        for candidate in request.candidates:
            candidate_text = " ".join(
                part
                for part in (
                    candidate.title,
                    candidate.reference or "",
                    candidate.description or "",
                    candidate.type.value,
                )
                if part
            )
            candidate_tokens = _tokenize(candidate_text)
            overlap = len(evidence_tokens & candidate_tokens)
            if overlap <= 0:
                continue
            if overlap >= 3:
                strength = ContextMatchStrength.HIGH
            elif overlap == 2:
                strength = ContextMatchStrength.MEDIUM
            else:
                strength = ContextMatchStrength.LOW
            scored.append(
                (
                    overlap,
                    candidate.business_context_id,
                    strength,
                    "Matched tokens from title/reference against analysis evidence.",
                )
            )

        scored.sort(key=lambda item: (-item[0], str(item[1])))
        suggestions = [
            BusinessContextSuggestionItem(
                business_context_id=context_id,
                match_strength=strength,
                rationale=rationale,
            )
            for _score, context_id, strength, rationale in scored[:_MAX_SUGGESTIONS]
        ]
        if not suggestions:
            return BusinessContextSuggestionResult(
                suggestions=[],
                no_match_reason="No suitable active context matched the analysis.",
                provider=self.PROVIDER_NAME,
            )
        return BusinessContextSuggestionResult(
            suggestions=suggestions,
            no_match_reason=None,
            provider=self.PROVIDER_NAME,
        )

    def _analyze_tabular(self, request: TabularAnalysisRequest) -> TabularAnalysisResult:
        """Build a deterministic advisory tabular result from fenced workbook text."""
        sheet_names = _extract_sheet_names(request.workbook_text)
        sheet_summaries = [
            TabularSheetSummary(
                sheet_name=name[:200],
                summary=f"Advisory sample summary for sheet '{name}'.",
            )
            for name in sheet_names[:10]
        ]
        haystack = request.workbook_text.lower()
        important_fields = _extract_header_fields(request.workbook_text)
        potential_dates = _collect_keyword_hits(
            request.workbook_text,
            (
                "due",
                "deadline",
                "date",
                "202",
            ),
            limit=15,
        )
        potential_amounts = _collect_keyword_hits(
            request.workbook_text,
            ("€", "$", "£", "amount", "total", "invoice"),
            limit=15,
        )
        potential_actions = _collect_keyword_hits(
            request.workbook_text,
            ("approve", "send", "pay", "review", "action", "please"),
            limit=15,
        )
        data_quality: list[str] = []
        if "formula:=" in haystack:
            data_quality.append("Formula text is present and treated as inert data.")
        if request.source_truncated:
            data_quality.append("Source sample was truncated before analysis.")

        limitations = [
            "Advisory extraction only; not a complete workbook audit.",
        ]
        if request.source_truncated:
            limitations.append(
                "Analysis covers only the bounded sample; completeness is not claimed."
            )

        warnings = list(request.parser_warnings[:20])
        if "https://" in haystack or "http://" in haystack:
            warnings.append("URL-like text observed; URLs were not followed.")

        summary = (
            f"Advisory tabular summary over {len(sheet_names) or 'unspecified'} "
            f"sheet(s); input_chars={request.input_character_count}."
        )
        return TabularAnalysisResult(
            summary=summary[:2000],
            sheet_summaries=sheet_summaries,
            important_fields=important_fields[:20],
            notable_values_or_patterns=[],
            data_quality_observations=data_quality[:15],
            potential_dates=potential_dates,
            potential_amounts=potential_amounts,
            potential_action_mentions=potential_actions,
            warnings=warnings[:20],
            limitations=limitations[:10],
            source_truncated=request.source_truncated,
            provider=self.PROVIDER_NAME,
        )


def _extract_sheet_names(workbook_text: str) -> list[str]:
    names: list[str] = []
    for line in workbook_text.splitlines():
        if line.startswith("name: "):
            names.append(line[len("name: ") :].strip() or "(unnamed)")
    return names


def _extract_header_fields(workbook_text: str) -> list[str]:
    fields: list[str] = []
    for line in workbook_text.splitlines():
        if line.startswith("header: "):
            for part in line[len("header: ") :].split(" | "):
                cleaned = part.strip()
                if cleaned and cleaned not in fields:
                    fields.append(cleaned[:200])
                if len(fields) >= 20:
                    return fields
    return fields


def _collect_keyword_hits(text: str, keywords: tuple[str, ...], *, limit: int) -> list[str]:
    hits: list[str] = []
    lower = text.lower()
    for keyword in keywords:
        if keyword.lower() in lower and keyword not in hits:
            hits.append(f"Observed advisory signal: {keyword}")
        if len(hits) >= limit:
            break
    return hits


def _tokenize(text: str) -> set[str]:
    """Return lowercase alphanumeric tokens of length >= 3."""
    tokens: set[str] = set()
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
            continue
        if len(current) >= 3:
            tokens.add("".join(current))
        current = []
    if len(current) >= 3:
        tokens.add("".join(current))
    return tokens


def _combined_text(request: CommunicationRequest) -> str:
    """Build a lowercase search corpus from distinguishable untrusted sections."""
    message = request.message
    subject = message.metadata.subject or ""
    sections = [
        "untrusted-email",
        subject,
        message.body,
    ]
    for attachment in request.attachment_texts:
        sections.extend(
            [
                "untrusted-attachment",
                attachment.media_kind.value,
                attachment.text,
            ]
        )
    if request.attachment_images:
        sections.append("untrusted-image")
    return "\n".join(sections).lower()


def _build_summary(request: CommunicationRequest) -> Summary:
    """Create a short deterministic summary from subject, body, or attachment."""
    message = request.message
    if request.attachment_images and not request.attachment_texts:
        text = "Summary: untrusted image attachment"
    elif request.attachment_texts:
        kind = request.attachment_texts[0].media_kind.value
        label = message.metadata.subject or "attachment"
        text = f"Summary: untrusted {kind} attachment ({label})"
    elif message.metadata.subject:
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
