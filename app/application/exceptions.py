"""Application-layer exceptions for use-case orchestration."""

from app.core.exceptions import ECIPlatformError


class AnalysisFailedError(ECIPlatformError):
    """Raised when an AI provider fails to analyze a communication."""
