"""Explicit attachment inspect → CLEAN scan → parse → untrusted AI request.

This service does not persist bytes, expose HTTP, create workflow actions,
or mutate connector state. It has no Propose/Approve/Execute/Send path.
"""

from __future__ import annotations

from app.application.exceptions import (
    AnalysisFailedError,
    AttachmentImageAnalysisNotAvailableError,
    AttachmentNotSupportedError,
    AttachmentProcessingError,
    AttachmentScanRejectedError,
)
from app.application.exceptions import (
    AttachmentExceedsLimitError as ApplicationAttachmentExceedsLimitError,
)
from app.application.services.attachment_inspection import AttachmentInspectionService
from app.application.services.communication_analysis import CommunicationAnalysisService
from app.core.logging import get_logger
from app.domain.attachment_policy import AttachmentContentBudget, attachment_size_bucket
from app.domain.enums import (
    AttachmentExtractedContentStatus,
    AttachmentKind,
    AttachmentScanVerdict,
)
from app.domain.exceptions import (
    AttachmentEncryptedError,
    AttachmentExceedsLimitError,
    AttachmentImageInputUnsupportedError,
    AttachmentNoExtractableTextError,
    AttachmentParseError,
    AttachmentUnsupportedError,
)
from app.domain.interfaces import AttachmentParser, CommunicationConnector
from app.domain.models import (
    AttachmentAnalysis,
    AttachmentTextSection,
    CommunicationMessage,
    ParsedAttachment,
)
from app.domain.schemas import CommunicationRequest

logger = get_logger(__name__)

_IMAGE_KINDS = frozenset({AttachmentKind.JPEG, AttachmentKind.PNG})


class AttachmentAnalysisService:
    """Orchestrate one explicit attachment analysis after a CLEAN scan."""

    def __init__(
        self,
        inspection: AttachmentInspectionService,
        parser: AttachmentParser,
        analysis: CommunicationAnalysisService,
        *,
        image_input_enabled: bool = False,
    ) -> None:
        self._inspection = inspection
        self._parser = parser
        self._analysis = analysis
        self._image_input_enabled = image_input_enabled

    def analyze(
        self,
        connector: CommunicationConnector,
        provider_message_id: str,
        provider_attachment_id: str,
        message: CommunicationMessage,
        *,
        budget: AttachmentContentBudget | None = None,
    ) -> AttachmentAnalysis:
        """Inspect, parse, and analyze exactly one CLEAN attachment."""
        inspected = self._inspection.inspect(
            connector,
            provider_message_id,
            provider_attachment_id,
            budget=budget,
            before_retrieve=self._reject_unavailable_image_kind,
        )
        if inspected.scan.verdict is not AttachmentScanVerdict.CLEAN:
            raise AttachmentScanRejectedError()

        size_bucket = attachment_size_bucket(len(inspected.content.content))
        try:
            parsed = self._parser.parse(inspected.content, inspected.kind)
        except AttachmentEncryptedError as exc:
            logger.info(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="encrypted",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise AttachmentNotSupportedError() from exc
        except AttachmentNoExtractableTextError as exc:
            logger.info(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="no_extractable_text",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise AttachmentNotSupportedError() from exc
        except AttachmentUnsupportedError as exc:
            logger.info(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="unsupported",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise AttachmentNotSupportedError() from exc
        except AttachmentExceedsLimitError as exc:
            logger.info(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="exceeds_limit",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise ApplicationAttachmentExceedsLimitError() from exc
        except AttachmentParseError as exc:
            logger.info(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="parser_error",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise AttachmentProcessingError() from exc
        except Exception:
            logger.warning(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="parser_error",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise AttachmentProcessingError() from None

        logger.info(
            "attachment_parse_completed",
            operation="analyze_attachment",
            provider=connector.provider,
            result="parsed",
            size_bucket=size_bucket,
            kind=inspected.kind.value,
            truncated=parsed.truncated,
        )

        request = _build_untrusted_request(message, parsed)
        # Defense in depth: capability was already gated before content retrieval.
        if request.attachment_images:
            self._reject_unavailable_image_kind(inspected.kind)

        logger.info(
            "attachment_ai_started",
            operation="analyze_attachment",
            provider=connector.provider,
            size_bucket=size_bucket,
            kind=inspected.kind.value,
        )
        try:
            result = self._analysis.analyze(request)
        except AnalysisFailedError:
            logger.warning(
                "attachment_ai_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="analysis_failed",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise
        except AttachmentImageInputUnsupportedError as exc:
            logger.info(
                "attachment_ai_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="image_unavailable",
                size_bucket=size_bucket,
                kind=inspected.kind.value,
            )
            raise AttachmentImageAnalysisNotAvailableError() from exc

        status = _extracted_status(parsed)
        logger.info(
            "attachment_ai_completed",
            operation="analyze_attachment",
            provider=result.provider,
            result="analyzed",
            size_bucket=size_bucket,
            kind=inspected.kind.value,
            extracted_status=status.value,
            truncated=parsed.truncated,
        )
        return AttachmentAnalysis(
            source_message_id=inspected.content.source_message_id,
            source_attachment_id=inspected.content.source_attachment_id,
            filename=inspected.content.metadata.filename,
            media_type=inspected.content.metadata.media_type,
            kind=inspected.kind,
            extracted_content_status=status,
            truncated=parsed.truncated,
            warnings=parsed.warnings,
            page_count=parsed.page_count,
            character_count=parsed.character_count,
            analysis=result.analysis.model_copy(update={"draft_reply": None}),
            provider=result.provider,
        )

    def _reject_unavailable_image_kind(self, kind: AttachmentKind) -> None:
        """Fail closed for JPEG/PNG when image AI is not configured or not declared."""
        if kind not in _IMAGE_KINDS:
            return
        if self._image_input_enabled and self._analysis.supports_image_input():
            return
        logger.info(
            "attachment_image_capability_rejected",
            operation="analyze_attachment",
            result="image_unavailable",
            kind=kind.value,
        )
        raise AttachmentImageAnalysisNotAvailableError()


def _build_untrusted_request(
    message: CommunicationMessage,
    parsed: ParsedAttachment,
) -> CommunicationRequest:
    attachment_texts: list[AttachmentTextSection] = []
    if parsed.extracted_text:
        attachment_texts.append(
            AttachmentTextSection(
                media_kind=parsed.kind,
                text=parsed.extracted_text,
                truncated=parsed.truncated,
            )
        )
    return CommunicationRequest(
        message=message,
        include_draft_reply=False,
        include_action_items=True,
        attachment_texts=attachment_texts,
        attachment_images=[parsed.image] if parsed.image is not None else [],
    )


def _extracted_status(parsed: ParsedAttachment) -> AttachmentExtractedContentStatus:
    if parsed.image is not None:
        return AttachmentExtractedContentStatus.IMAGE
    if parsed.truncated:
        return AttachmentExtractedContentStatus.TRUNCATED_TEXT
    return AttachmentExtractedContentStatus.TEXT
