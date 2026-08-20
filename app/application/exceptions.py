"""Application-layer exceptions for use-case orchestration."""

from app.core.exceptions import ECIPlatformError


class AnalysisFailedError(ECIPlatformError):
    """Raised when an AI provider fails to analyze a communication."""


class AnalysisNotFoundError(ECIPlatformError):
    """Raised when an analysis is unknown or not owned by the caller."""

    def __init__(self) -> None:
        super().__init__("Analysis not found.")


class ConnectorAccountNotFoundError(ECIPlatformError):
    """Raised when a connector account is unknown or not owned by the caller."""

    def __init__(self) -> None:
        super().__init__("Connector account not found.")


class ConnectorAccountInvalidRequestError(ECIPlatformError):
    """Raised when connector-account input cannot be accepted."""

    def __init__(self) -> None:
        super().__init__("Connector account request is invalid.")
