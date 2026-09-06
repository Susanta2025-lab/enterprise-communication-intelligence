"""Construct the configured attachment scanner.

FakeAttachmentScanner is test/offline infrastructure only. Production must
not interpret a fake CLEAN verdict as malware clearance. ClamAV binaries
are not installed in the API process; only a client adapter is constructed.
"""

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.domain.interfaces.attachment_scanner import AttachmentScanner
from app.infrastructure.attachments.clamav_scanner import ClamAVAttachmentScanner
from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner
from app.infrastructure.attachments.unavailable_scanner import UnavailableAttachmentScanner


def create_attachment_scanner(settings: Settings) -> AttachmentScanner:
    """Return the configured scanner, failing closed unless fake or clamav.

    ``none`` (default) yields ``UnavailableAttachmentScanner``. ``fake`` is
    allowed only when ``APP_ENV`` is not ``production``. ``clamav`` requires
    an explicit host. Unknown backends are rejected by Settings.
    """
    backend = settings.attachment_scanner_backend
    if backend == "fake":
        if settings.app_env == "production":
            raise ConfigurationError(
                "ATTACHMENT_SCANNER_BACKEND must not be fake when APP_ENV=production."
            )
        return FakeAttachmentScanner()
    if backend == "clamav":
        host = settings.attachment_scanner_host
        if host is None:
            raise ConfigurationError(
                "ATTACHMENT_SCANNER_HOST must be set when ATTACHMENT_SCANNER_BACKEND=clamav."
            )
        return ClamAVAttachmentScanner(
            host,
            settings.attachment_scanner_port,
            settings.attachment_scanner_timeout_seconds,
        )
    if backend == "none":
        return UnavailableAttachmentScanner()
    raise ConfigurationError("ATTACHMENT_SCANNER_BACKEND is not supported.")
