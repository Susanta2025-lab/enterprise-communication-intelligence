"""Domain exceptions that do not depend on application or infrastructure layers."""

from app.domain.enums import AttachmentScanVerdict


class InvalidWorkflowTransitionError(Exception):
    """Raised when a workflow action cannot move to the requested status."""

    def __init__(self) -> None:
        self.message = "Invalid workflow state transition."
        super().__init__(self.message)


class AttachmentUnsupportedError(Exception):
    """Raised when type, MIME, extension, or signature policy rejects an attachment."""

    def __init__(self, message: str = "Attachment is not supported.") -> None:
        self.message = message
        super().__init__(self.message)


class AttachmentExceedsLimitError(Exception):
    """Raised when reported or actual attachment size exceeds ECI limits."""

    def __init__(self, message: str = "Attachment exceeds limits.") -> None:
        self.message = message
        super().__init__(self.message)


class AttachmentContentInvalidError(Exception):
    """Raised when retrieved attachment bytes are malformed or inconsistent."""

    def __init__(self, message: str = "Attachment content is invalid.") -> None:
        self.message = message
        super().__init__(self.message)


class AttachmentScanRejectedError(Exception):
    """Raised when a completed scan is not CLEAN (malicious or unknown)."""

    def __init__(
        self,
        verdict: AttachmentScanVerdict,
        message: str = "Attachment could not be processed.",
    ) -> None:
        self.verdict = verdict
        self.message = message
        super().__init__(self.message)


class AttachmentScannerUnavailableError(Exception):
    """Raised when the scanner cannot complete an operational scan."""

    def __init__(self, message: str = "Attachment scanner is unavailable.") -> None:
        self.message = message
        super().__init__(self.message)
