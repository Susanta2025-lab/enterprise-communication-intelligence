"""Application-layer exceptions for use-case orchestration."""

from app.core.exceptions import ContextMeshError


class AnalysisFailedError(ContextMeshError):
    """Raised when an AI provider fails to analyze a communication."""
