"""Provider-neutral parse/extract port for already-scanned attachments."""

from abc import ABC, abstractmethod

from app.domain.enums import AttachmentKind
from app.domain.models.attachment import AttachmentContent, ParsedAttachment


class AttachmentParser(ABC):
    """Extract a provider-neutral representation from CLEAN attachment bytes.

    Callers must not invoke this port unless the scan verdict is ``CLEAN``.
    Implementations must not persist bytes or follow external resources.
    """

    @abstractmethod
    def parse(self, content: AttachmentContent, kind: AttachmentKind) -> ParsedAttachment:
        """Return extracted text or a bounded image descriptor."""
