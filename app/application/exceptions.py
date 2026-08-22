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


class WorkflowActionNotFoundError(ECIPlatformError):
    """Raised when a workflow action is unknown or not owned by the caller."""

    def __init__(self) -> None:
        super().__init__("Workflow action not found.")


class WorkflowActionConflictError(ECIPlatformError):
    """Raised when a conditional workflow update no longer matches stored status."""

    def __init__(self) -> None:
        super().__init__("Workflow action was updated concurrently.")


class AnalysisHasNoDraftReplyError(ECIPlatformError):
    """Raised when an owned analysis has no usable draft reply to snapshot."""

    def __init__(self) -> None:
        super().__init__("Analysis has no usable draft reply.")


class WorkflowActionNotExecutableError(ECIPlatformError):
    """Raised when an owned action cannot begin external execution.

    Covers missing execution targets and unusable mailbox accounts. The
    public message does not distinguish those cases.
    """

    def __init__(self) -> None:
        super().__init__("Workflow action is not executable.")
