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
from app.domain.enums import AttachmentExtractedContentStatus, AttachmentScanVerdict
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
        )
        if inspected.scan.verdict is not AttachmentScanVerdict.CLEAN:
            raise AttachmentScanRejectedError()

        try:
            parsed = self._parser.parse(inspected.content, inspected.kind)
        except AttachmentEncryptedError as exc:
            raise AttachmentNotSupportedError() from exc
        except AttachmentNoExtractableTextError as exc:
            raise AttachmentNotSupportedError() from exc
        except AttachmentUnsupportedError as exc:
            raise AttachmentNotSupportedError() from exc
        except AttachmentExceedsLimitError as exc:
            raise ApplicationAttachmentExceedsLimitError() from exc
        except AttachmentParseError as exc:
            raise AttachmentProcessingError() from exc
        except Exception:
            logger.warning(
                "attachment_parse_failed",
                operation="analyze_attachment",
                provider=connector.provider,
                result="parser_error",
                size_bucket=attachment_size_bucket(len(inspected.content.content)),
                kind=inspected.kind.value,
            )
            raise AttachmentProcessingError() from None

        request = _build_untrusted_request(message, parsed)
        if request.attachment_images:
            if not self._image_input_enabled or not self._analysis.supports_image_input():
                raise AttachmentImageAnalysisNotAvailableError()

        try:
            result = self._analysis.analyze(request)
        except AnalysisFailedError:
            raise
        except AttachmentImageInputUnsupportedError as exc:
            raise AttachmentImageAnalysisNotAvailableError() from exc

        status = _extracted_status(parsed)
        logger.info(
            "attachment_analysis_completed",
            operation="analyze_attachment",
            provider=result.provider,
            result="analyzed",
            size_bucket=attachment_size_bucket(len(inspected.content.content)),
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
