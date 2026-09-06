"""Provider-neutral malware-scan port for transient attachment bytes."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AttachmentScanVerdict
from app.domain.models.attachment import AttachmentContent


class AttachmentScanResult(BaseModel):
    """Completed or failed scan outcome. Never includes bytes or filenames."""

    model_config = ConfigDict(extra="forbid")

    verdict: AttachmentScanVerdict


class AttachmentScanner(ABC):
    """Scan one already-retrieved attachment. Implementations stay offline or sidecar.

    A real production attachment must not proceed to parse/AI unless the
    verdict is ``CLEAN``. ``FakeAttachmentScanner`` is not malware protection.
    """

    @abstractmethod
    def scan(self, content: AttachmentContent) -> AttachmentScanResult:
        """Return a fail-closed verdict for one transient attachment."""
