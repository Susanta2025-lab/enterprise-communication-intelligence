"""Deterministic offline scanner for tests and local development.

This is not malware protection. Production attachment analysis must not
use this backend.
"""

from collections.abc import Mapping

from app.domain.enums import AttachmentScanVerdict
from app.domain.interfaces.attachment_scanner import AttachmentScanner, AttachmentScanResult
from app.domain.models.attachment import AttachmentContent

CLEAN_FIXTURE_LABEL = b"ECI-SCAN-CLEAN"
MALICIOUS_FIXTURE_LABEL = b"ECI-SCAN-MALICIOUS"
UNKNOWN_FIXTURE_LABEL = b"ECI-SCAN-UNKNOWN"
FAILURE_FIXTURE_LABEL = b"ECI-SCAN-FAILURE"


class FakeAttachmentScanner(AttachmentScanner):
    """Programmable scanner that recognizes fixture labels, never live malware.

    Verdicts may be forced by ``(source_message_id, source_attachment_id)``.
    Unprogrammed content uses embedded fixture labels, then ``default_verdict``.
    """

    def __init__(
        self,
        *,
        default_verdict: AttachmentScanVerdict = AttachmentScanVerdict.CLEAN,
        verdicts: Mapping[tuple[str, str], AttachmentScanVerdict] | None = None,
        raise_on_scan: Exception | None = None,
    ) -> None:
        self._default_verdict = default_verdict
        self._verdicts = dict(verdicts or {})
        self._raise_on_scan = raise_on_scan

    def scan(self, content: AttachmentContent) -> AttachmentScanResult:
        """Return a deterministic verdict without inspecting as an AV engine."""
        if self._raise_on_scan is not None:
            raise self._raise_on_scan
        key = (content.source_message_id, content.source_attachment_id)
        if key in self._verdicts:
            return AttachmentScanResult(verdict=self._verdicts[key])
        payload = content.content
        if FAILURE_FIXTURE_LABEL in payload:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.ERROR)
        if MALICIOUS_FIXTURE_LABEL in payload:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.MALICIOUS)
        if UNKNOWN_FIXTURE_LABEL in payload:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.UNKNOWN)
        if CLEAN_FIXTURE_LABEL in payload:
            return AttachmentScanResult(verdict=AttachmentScanVerdict.CLEAN)
        return AttachmentScanResult(verdict=self._default_verdict)
