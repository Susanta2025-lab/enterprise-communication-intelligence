"""Explicit single-attachment retrieve → policy → scan.

This service does not parse documents, invoke AI, persist bytes, or expose
HTTP. 18D must obtain the connector only after:

1. Authenticated principal ``(iss, sub)``
2. Owned ``connector_accounts.id``
3. ``ACTIVE`` + ``mail.read``
4. Provider message id belonging to that mailbox
5. Provider attachment id listed on that message

Filename, display email, MIME type, and provider URLs are not authorization
keys. Connector methods cannot prove ECI user ownership; that check stays
in the 18D application/API wiring that constructs the connector.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.application.exceptions import (
    AttachmentContentInvalidError as ApplicationAttachmentContentInvalidError,
)
from app.application.exceptions import (
    AttachmentExceedsLimitError as ApplicationAttachmentExceedsLimitError,
)
from app.application.exceptions import (
    AttachmentNotSupportedError,
    AttachmentScannerUnavailableError,
    AttachmentScanRejectedError,
    MailboxAttachmentNotFoundError,
    MailboxMessageNotFoundError,
)
from app.core.exceptions import (
    ConnectorAttachmentContentError,
    ConnectorAttachmentMetadataError,
    ConnectorAttachmentNotFoundError,
    ConnectorMessageNotFoundError,
    ConnectorUnsupportedAttachmentError,
)
from app.core.logging import get_logger
from app.domain.attachment_policy import (
    AttachmentContentBudget,
    attachment_size_bucket,
    evaluate_attachment_content,
    evaluate_attachment_metadata,
)
from app.domain.enums import AttachmentKind, AttachmentScanVerdict
from app.domain.exceptions import (
    AttachmentContentInvalidError,
    AttachmentExceedsLimitError,
    AttachmentUnsupportedError,
)
from app.domain.exceptions import (
    AttachmentScannerUnavailableError as DomainScannerUnavailableError,
)
from app.domain.interfaces import CommunicationConnector
from app.domain.interfaces.attachment_scanner import AttachmentScanner, AttachmentScanResult
from app.domain.models import AttachmentContent, AttachmentMetadata

logger = get_logger(__name__)


class InspectedAttachment(BaseModel):
    """Transient retrieve+scan result. Contains bytes; never persist this object."""

    model_config = ConfigDict(extra="forbid")

    content: AttachmentContent
    kind: AttachmentKind
    scan: AttachmentScanResult


class AttachmentInspectionService:
    """Enforce metadata pre-check → one retrieve → size/type → scanner → STOP."""

    def __init__(self, scanner: AttachmentScanner) -> None:
        self._scanner = scanner

    def inspect(
        self,
        connector: CommunicationConnector,
        provider_message_id: str,
        provider_attachment_id: str,
        *,
        budget: AttachmentContentBudget | None = None,
    ) -> InspectedAttachment:
        """Retrieve and scan exactly one attachment already bound to ``connector``."""
        message_id = _require_id(provider_message_id, missing_message=True)
        attachment_id = _require_id(provider_attachment_id, missing_message=False)
        try:
            page = connector.list_attachments(message_id)
        except ConnectorMessageNotFoundError:
            raise MailboxMessageNotFoundError() from None
        except ConnectorUnsupportedAttachmentError:
            raise AttachmentNotSupportedError() from None
        except ConnectorAttachmentMetadataError:
            raise ApplicationAttachmentContentInvalidError() from None
        metadata = _attachment_on_message(page.items, attachment_id)
        try:
            evaluate_attachment_metadata(metadata)
        except AttachmentUnsupportedError:
            raise AttachmentNotSupportedError() from None
        except AttachmentExceedsLimitError:
            raise ApplicationAttachmentExceedsLimitError() from None
        except AttachmentContentInvalidError:
            raise ApplicationAttachmentContentInvalidError() from None

        try:
            content = connector.fetch_attachment_content(message_id, attachment_id)
        except ConnectorMessageNotFoundError:
            raise MailboxMessageNotFoundError() from None
        except ConnectorAttachmentNotFoundError:
            raise MailboxAttachmentNotFoundError() from None
        except ConnectorUnsupportedAttachmentError:
            raise AttachmentNotSupportedError() from None
        except (ConnectorAttachmentContentError, ConnectorAttachmentMetadataError):
            raise ApplicationAttachmentContentInvalidError() from None

        if content.source_message_id != message_id:
            raise MailboxAttachmentNotFoundError()
        if content.source_attachment_id != attachment_id:
            raise MailboxAttachmentNotFoundError()

        try:
            kind = evaluate_attachment_content(content)
        except AttachmentUnsupportedError:
            raise AttachmentNotSupportedError() from None
        except AttachmentExceedsLimitError:
            raise ApplicationAttachmentExceedsLimitError() from None
        except AttachmentContentInvalidError:
            raise ApplicationAttachmentContentInvalidError() from None

        active_budget = budget if budget is not None else AttachmentContentBudget()
        try:
            active_budget.consume(len(content.content))
        except AttachmentExceedsLimitError:
            raise ApplicationAttachmentExceedsLimitError() from None

        try:
            scan = self._scanner.scan(content)
        except DomainScannerUnavailableError:
            raise AttachmentScannerUnavailableError() from None
        except Exception:
            logger.warning(
                "attachment_scan_failed",
                operation="inspect_attachment",
                provider=connector.provider,
                result="scanner_error",
                size_bucket=attachment_size_bucket(len(content.content)),
            )
            raise AttachmentScannerUnavailableError() from None

        if scan.verdict is AttachmentScanVerdict.ERROR:
            raise AttachmentScannerUnavailableError()
        if scan.verdict is not AttachmentScanVerdict.CLEAN:
            logger.info(
                "attachment_scan_rejected",
                operation="inspect_attachment",
                provider=connector.provider,
                result=scan.verdict.value,
                size_bucket=attachment_size_bucket(len(content.content)),
            )
            raise AttachmentScanRejectedError()

        logger.info(
            "attachment_inspection_completed",
            operation="inspect_attachment",
            provider=connector.provider,
            result="clean",
            size_bucket=attachment_size_bucket(len(content.content)),
            kind=kind.value,
        )
        return InspectedAttachment(content=content, kind=kind, scan=scan)


def _attachment_on_message(
    items: list[AttachmentMetadata],
    provider_attachment_id: str,
) -> AttachmentMetadata:
    matches = [
        item for item in items if item.provider_attachment_id == provider_attachment_id
    ]
    if len(matches) != 1:
        raise MailboxAttachmentNotFoundError()
    return matches[0]


def _require_id(value: str, *, missing_message: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        if missing_message:
            raise MailboxMessageNotFoundError()
        raise MailboxAttachmentNotFoundError()
    return value.strip()
