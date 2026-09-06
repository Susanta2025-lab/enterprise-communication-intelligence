"""Fail-closed retrieve → policy → scan orchestration. No parse. No AI."""

from __future__ import annotations

import pytest

from app.application.exceptions import (
    AttachmentExceedsLimitError,
    AttachmentNotSupportedError,
    AttachmentScannerUnavailableError,
    AttachmentScanRejectedError,
    MailboxAttachmentNotFoundError,
    MailboxMessageNotFoundError,
)
from app.application.services.attachment_inspection import (
    AttachmentInspectionService,
    InspectedAttachment,
)
from app.domain.attachment_policy import MAX_ATTACHMENT_CONTENT_BYTES, AttachmentContentBudget
from app.domain.enums import AttachmentKind, AttachmentScanVerdict
from app.domain.models import AttachmentContent, AttachmentMetadata
from app.infrastructure.attachments import FakeAttachmentScanner
from app.infrastructure.attachments.fake_scanner import (
    FAILURE_FIXTURE_LABEL,
    MALICIOUS_FIXTURE_LABEL,
    UNKNOWN_FIXTURE_LABEL,
)
from app.infrastructure.connectors.fake import FakeCommunicationConnector


def _pdf_metadata(attachment_id: str = "att-1", *, size: int = 24) -> AttachmentMetadata:
    return AttachmentMetadata(
        provider_attachment_id=attachment_id,
        filename="report.pdf",
        media_type="application/pdf",
        reported_size=size,
    )


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def _connector(
    *,
    attachments: dict[str, tuple[AttachmentMetadata, ...]] | None = None,
    contents: dict[tuple[str, str], bytes] | None = None,
) -> FakeCommunicationConnector:
    return FakeCommunicationConnector(
        attachments=attachments or {"fake-msg-001": (_pdf_metadata(size=len(_pdf_bytes())),)},
        attachment_contents=contents or {("fake-msg-001", "att-1"): _pdf_bytes()},
    )


def test_inspect_clean_pdf_stops_before_parse_and_ai() -> None:
    service = AttachmentInspectionService(FakeAttachmentScanner())
    result = service.inspect(_connector(), "fake-msg-001", "att-1")

    assert result.kind is AttachmentKind.PDF
    assert result.scan.verdict is AttachmentScanVerdict.CLEAN
    assert result.content.content == _pdf_bytes()
    assert "text" not in InspectedAttachment.model_fields
    assert "parsed" not in InspectedAttachment.model_fields


def test_inspect_requires_attachment_id_on_that_message() -> None:
    service = AttachmentInspectionService(FakeAttachmentScanner())
    with pytest.raises(MailboxAttachmentNotFoundError):
        service.inspect(_connector(), "fake-msg-001", "att-other")
    with pytest.raises(MailboxMessageNotFoundError):
        service.inspect(_connector(), "missing-message", "att-1")


def test_inspect_does_not_authorize_by_filename() -> None:
    service = AttachmentInspectionService(FakeAttachmentScanner())
    with pytest.raises(MailboxAttachmentNotFoundError):
        service.inspect(_connector(), "fake-msg-001", "report.pdf")


def test_inspect_rejects_unsupported_before_fetch() -> None:
    class _Guard(FakeCommunicationConnector):
        def fetch_attachment_content(
            self,
            provider_message_id: str,
            provider_attachment_id: str,
        ) -> AttachmentContent:
            raise AssertionError("unsupported metadata must not retrieve bytes")

    connector = _Guard(
        attachments={
            "fake-msg-001": (
                AttachmentMetadata(
                    provider_attachment_id="att-zip",
                    filename="archive.zip",
                    media_type="application/zip",
                    reported_size=12,
                ),
            )
        },
        attachment_contents={("fake-msg-001", "att-zip"): b"PK\x03\x04"},
    )
    service = AttachmentInspectionService(FakeAttachmentScanner())
    with pytest.raises(AttachmentNotSupportedError):
        service.inspect(connector, "fake-msg-001", "att-zip")


def test_inspect_rejects_oversized_metadata_before_fetch() -> None:
    class _Guard(FakeCommunicationConnector):
        def fetch_attachment_content(
            self,
            provider_message_id: str,
            provider_attachment_id: str,
        ) -> AttachmentContent:
            raise AssertionError("oversized metadata must not retrieve bytes")

    connector = _Guard(
        attachments={
            "fake-msg-001": (
                _pdf_metadata(size=MAX_ATTACHMENT_CONTENT_BYTES + 1),
            )
        }
    )
    service = AttachmentInspectionService(FakeAttachmentScanner())
    with pytest.raises(AttachmentExceedsLimitError):
        service.inspect(connector, "fake-msg-001", "att-1")


def test_inspect_malicious_unknown_and_scanner_failure_fail_closed() -> None:
    payload = _pdf_bytes()
    service = AttachmentInspectionService(FakeAttachmentScanner())
    malicious = _connector(
        attachments={"fake-msg-001": (_pdf_metadata(size=len(payload + MALICIOUS_FIXTURE_LABEL)),)},
        contents={("fake-msg-001", "att-1"): payload + MALICIOUS_FIXTURE_LABEL},
    )
    with pytest.raises(AttachmentScanRejectedError):
        service.inspect(malicious, "fake-msg-001", "att-1")

    unknown = _connector(
        attachments={"fake-msg-001": (_pdf_metadata(size=len(payload + UNKNOWN_FIXTURE_LABEL)),)},
        contents={("fake-msg-001", "att-1"): payload + UNKNOWN_FIXTURE_LABEL},
    )
    with pytest.raises(AttachmentScanRejectedError):
        service.inspect(unknown, "fake-msg-001", "att-1")

    failed = _connector(
        attachments={"fake-msg-001": (_pdf_metadata(size=len(payload + FAILURE_FIXTURE_LABEL)),)},
        contents={("fake-msg-001", "att-1"): payload + FAILURE_FIXTURE_LABEL},
    )
    with pytest.raises(AttachmentScannerUnavailableError):
        service.inspect(failed, "fake-msg-001", "att-1")

    raising = AttachmentInspectionService(
        FakeAttachmentScanner(raise_on_scan=RuntimeError("offline"))
    )
    with pytest.raises(AttachmentScannerUnavailableError) as exc_info:
        raising.inspect(_connector(), "fake-msg-001", "att-1")
    assert "offline" not in exc_info.value.message


def test_inspect_session_budget_is_in_memory_only() -> None:
    service = AttachmentInspectionService(FakeAttachmentScanner())
    budget = AttachmentContentBudget(limit_bytes=len(_pdf_bytes()))
    service.inspect(_connector(), "fake-msg-001", "att-1", budget=budget)
    with pytest.raises(AttachmentExceedsLimitError):
        service.inspect(_connector(), "fake-msg-001", "att-1", budget=budget)


def test_inspect_does_not_list_or_fetch_sibling_content() -> None:
    sibling = _pdf_metadata("att-2", size=len(_pdf_bytes()))

    class _Watch(FakeCommunicationConnector):
        def fetch_attachment_content(
            self,
            provider_message_id: str,
            provider_attachment_id: str,
        ) -> AttachmentContent:
            self.fetched.append((provider_message_id, provider_attachment_id))
            return super().fetch_attachment_content(
                provider_message_id,
                provider_attachment_id,
            )

    watched = _Watch(
        attachments={"fake-msg-001": (_pdf_metadata(size=len(_pdf_bytes())), sibling)},
        attachment_contents={
            ("fake-msg-001", "att-1"): _pdf_bytes(),
            ("fake-msg-001", "att-2"): _pdf_bytes() + b"%PDF-sibling",
        },
    )
    watched.fetched = []
    result = AttachmentInspectionService(FakeAttachmentScanner()).inspect(
        watched,
        "fake-msg-001",
        "att-1",
    )
    assert watched.fetched == [("fake-msg-001", "att-1")]
    assert result.content.source_attachment_id == "att-1"
    assert b"sibling" not in result.content.content


def test_inspection_service_does_not_depend_on_ai_or_http() -> None:
    import app.application.services.attachment_inspection as module

    names = set(module.__dict__)
    assert "AIProvider" not in names
    assert "httpx" not in names
    assert "CommunicationConnector" in names
