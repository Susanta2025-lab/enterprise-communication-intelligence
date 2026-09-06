"""Fail-closed scanner used when no real malware backend is configured.

This is not malware protection. It never returns CLEAN. Production and the
default configuration must use this adapter rather than FakeAttachmentScanner.
"""

from app.domain.enums import AttachmentScanVerdict
from app.domain.interfaces.attachment_scanner import AttachmentScanner, AttachmentScanResult
from app.domain.models.attachment import AttachmentContent


class UnavailableAttachmentScanner(AttachmentScanner):
    """Operational scanner stand-in that always reports ERROR."""

    def scan(self, content: AttachmentContent) -> AttachmentScanResult:
        """Refuse to treat the attachment as scanned or clean."""
        del content
        return AttachmentScanResult(verdict=AttachmentScanVerdict.ERROR)
