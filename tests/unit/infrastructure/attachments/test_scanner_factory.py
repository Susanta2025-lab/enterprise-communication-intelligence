"""Scanner factory fail-closed wiring."""

import pytest

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.domain.enums import AttachmentScanVerdict
from app.infrastructure.attachments.clamav_scanner import ClamAVAttachmentScanner
from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner
from app.infrastructure.attachments.scanner_factory import create_attachment_scanner
from app.infrastructure.attachments.unavailable_scanner import UnavailableAttachmentScanner
from tests.unit.infrastructure.attachments.fixtures import attachment_content, pdf_with_text


def test_default_settings_yield_unavailable_scanner() -> None:
    """The production/default path must not wire FakeAttachmentScanner."""
    settings = Settings(_env_file=None)
    scanner = create_attachment_scanner(settings)
    assert isinstance(scanner, UnavailableAttachmentScanner)
    assert not isinstance(scanner, FakeAttachmentScanner)
    content = attachment_content(
        pdf_with_text("x"),
        filename="a.pdf",
        media_type="application/pdf",
    )
    result = scanner.scan(content)
    assert result.verdict is AttachmentScanVerdict.ERROR


def test_explicit_fake_backend_is_available_in_development() -> None:
    """Offline development may opt into FakeScanner only through configuration."""
    settings = Settings(attachment_scanner_backend="fake", _env_file=None)
    scanner = create_attachment_scanner(settings)
    assert isinstance(scanner, FakeAttachmentScanner)


def test_clamav_backend_wires_client_adapter() -> None:
    settings = Settings(
        attachment_scanner_backend="clamav",
        attachment_scanner_host="clamav",
        _env_file=None,
    )
    scanner = create_attachment_scanner(settings)
    assert isinstance(scanner, ClamAVAttachmentScanner)
    assert not isinstance(scanner, FakeAttachmentScanner)


def test_clamav_factory_rejects_missing_host() -> None:
    settings = Settings.model_construct(attachment_scanner_backend="clamav")
    with pytest.raises(ConfigurationError):
        create_attachment_scanner(settings)
