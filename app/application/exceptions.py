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


class ConnectorAccountConflictError(ECIPlatformError):
    """Raised when a connector-account lifecycle operation is not allowed.

    Covers reauthorizing an ACTIVE account and other status conflicts.
    The public message does not distinguish those cases.
    """

    def __init__(self) -> None:
        super().__init__("Connector account cannot be updated.")


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


class MailboxAuthorizationSessionInvalidError(ECIPlatformError):
    """Raised when a mailbox authorization session cannot be used.

    Covers missing, expired, consumed, provider-mismatched, and malformed
    state without distinguishing those cases.
    """

    def __init__(self) -> None:
        super().__init__("Mailbox authorization session is invalid.")


class UnsupportedMailboxAuthorizationProviderError(ECIPlatformError):
    """Raised when mailbox authorization is requested for an unsupported provider."""

    def __init__(self) -> None:
        super().__init__("Mailbox authorization provider is not supported.")


class MailboxOAuthAuthorizationDeniedError(ECIPlatformError):
    """Raised when the mailbox provider reports consent denial."""

    def __init__(self) -> None:
        super().__init__("Mailbox authorization was denied.")


class WorkflowActionNotExecutableError(ECIPlatformError):
    """Raised when an owned action cannot begin external execution.

    Covers missing execution targets, unusable mailbox accounts, and
    factory routing that cannot produce a production writer. The public
    message does not distinguish those cases.
    """

    def __init__(self) -> None:
        super().__init__("Workflow action is not executable.")


class ConnectedMailboxNotAvailableError(ECIPlatformError):
    """Raised when an owned connector account cannot currently be used for mailbox read.

    Covers DISCONNECTED, REAUTH_REQUIRED, explicit missing ``mail.read``,
    unsupported or unroutable provider, and missing usable credential locator.
    The public message does not distinguish those cases. Unknown and
    cross-user accounts remain ``ConnectorAccountNotFoundError``.
    """

    def __init__(self) -> None:
        super().__init__("Connected mailbox is not available.")


class MailboxMessageNotFoundError(ECIPlatformError):
    """Raised when a provider message is unknown for an owned mailbox."""

    def __init__(self) -> None:
        super().__init__("Mailbox message not found.")
