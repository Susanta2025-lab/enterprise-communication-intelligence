"""Deterministic FakeAttachmentScanner tests. Not malware-protection claims."""

from pathlib import Path

import pytest

from app.domain.enums import AttachmentScanVerdict
from app.domain.interfaces.attachment_scanner import AttachmentScanner
from app.domain.models import AttachmentContent, AttachmentMetadata
from app.infrastructure.attachments import FakeAttachmentScanner
from app.infrastructure.attachments.fake_scanner import (
    CLEAN_FIXTURE_LABEL,
    FAILURE_FIXTURE_LABEL,
    MALICIOUS_FIXTURE_LABEL,
    UNKNOWN_FIXTURE_LABEL,
)

_FAKE_ROOT = Path(__file__).resolve().parents[4] / "app" / "infrastructure" / "attachments"


def _content(payload: bytes, attachment_id: str = "att-1") -> AttachmentContent:
    return AttachmentContent(
        metadata=AttachmentMetadata(
            provider_attachment_id=attachment_id,
            filename="report.pdf",
            media_type="application/pdf",
            reported_size=len(payload),
        ),
        content=payload,
        source_message_id="msg-1",
        source_attachment_id=attachment_id,
    )


def test_fake_scanner_is_an_attachment_scanner() -> None:
    scanner = FakeAttachmentScanner()
    assert isinstance(scanner, AttachmentScanner)


def test_fake_scanner_clean_malicious_unknown_and_failure_labels() -> None:
    scanner = FakeAttachmentScanner()
    assert scanner.scan(_content(CLEAN_FIXTURE_LABEL)).verdict is AttachmentScanVerdict.CLEAN
    assert (
        scanner.scan(_content(MALICIOUS_FIXTURE_LABEL)).verdict
        is AttachmentScanVerdict.MALICIOUS
    )
    assert scanner.scan(_content(UNKNOWN_FIXTURE_LABEL)).verdict is AttachmentScanVerdict.UNKNOWN
    assert scanner.scan(_content(FAILURE_FIXTURE_LABEL)).verdict is AttachmentScanVerdict.ERROR


def test_fake_scanner_programmed_verdict_overrides_default() -> None:
    scanner = FakeAttachmentScanner(
        default_verdict=AttachmentScanVerdict.CLEAN,
        verdicts={("msg-1", "att-bad"): AttachmentScanVerdict.MALICIOUS},
    )
    result = scanner.scan(_content(b"%PDF-1.4", attachment_id="att-bad"))
    assert result.verdict is AttachmentScanVerdict.MALICIOUS


def test_fake_scanner_can_raise_operational_failure() -> None:
    scanner = FakeAttachmentScanner(raise_on_scan=RuntimeError("scanner down"))
    with pytest.raises(RuntimeError, match="scanner down"):
        scanner.scan(_content(b"%PDF-1.4"))


def test_fake_scanner_source_does_not_claim_malware_protection() -> None:
    source = (_FAKE_ROOT / "fake_scanner.py").read_text(encoding="utf-8").lower()
    assert "not malware protection" in source
    assert "clamav" not in source
    assert "eicar" not in source
