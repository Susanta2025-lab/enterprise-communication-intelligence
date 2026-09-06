"""Construct the configured attachment scanner.

FakeAttachmentScanner is test/offline infrastructure only. Production must
not interpret a fake CLEAN verdict as malware clearance.
"""

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.domain.interfaces.attachment_scanner import AttachmentScanner
from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner
from app.infrastructure.attachments.unavailable_scanner import UnavailableAttachmentScanner


def create_attachment_scanner(settings: Settings) -> AttachmentScanner:
    """Return the configured scanner, failing closed unless fake is explicit.

    ``none`` (default) yields ``UnavailableAttachmentScanner``. ``fake`` is
    allowed only when ``APP_ENV`` is not ``production``.
    """
    if settings.attachment_scanner_backend == "fake":
        if settings.app_env == "production":
            raise ConfigurationError(
                "ATTACHMENT_SCANNER_BACKEND must not be fake when APP_ENV=production."
            )
        return FakeAttachmentScanner()
    return UnavailableAttachmentScanner()
