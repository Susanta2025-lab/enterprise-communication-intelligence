"""Unit tests for application exceptions."""

from app.application.exceptions import (
    AnalysisFailedError,
    AnalysisHasNoDraftReplyError,
    AnalysisNotFoundError,
    ConnectedMailboxNotAvailableError,
    ConnectorAccountConflictError,
    ConnectorAccountInvalidRequestError,
    ConnectorAccountNotFoundError,
    MailboxAuthorizationSessionInvalidError,
    MailboxMessageNotFoundError,
    MailboxOAuthAuthorizationDeniedError,
    UnsupportedMailboxAuthorizationProviderError,
    WorkflowActionConflictError,
    WorkflowActionNotExecutableError,
    WorkflowActionNotFoundError,
)
from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialConflictError,
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConfigurationError,
    ConnectorAuthenticationError,
    ConnectorError,
    ConnectorInvalidCursorError,
    ConnectorMessageContentError,
    ConnectorMessageNotFoundError,
    ConnectorPermissionError,
    ConnectorRateLimitError,
    ConnectorUnavailableError,
    ECIPlatformError,
    MailboxOAuthAuthorizationFailedError,
    PersistenceError,
    ServiceUnavailableError,
    UnsupportedCommunicationCredentialProviderError,
)
from app.domain.exceptions import InvalidWorkflowTransitionError


def test_exception_hierarchy() -> None:
    """Application exceptions should share a common base type."""
    assert issubclass(ConfigurationError, ECIPlatformError)
    assert issubclass(ServiceUnavailableError, ECIPlatformError)
    assert issubclass(PersistenceError, ECIPlatformError)
    assert issubclass(CommunicationActionExecutionError, ECIPlatformError)
    assert issubclass(CommunicationCredentialUnavailableError, ECIPlatformError)
    assert issubclass(
        CommunicationCredentialReauthorizationRequiredError,
        CommunicationCredentialUnavailableError,
    )
    assert issubclass(CommunicationCredentialConflictError, ECIPlatformError)
    assert issubclass(UnsupportedCommunicationCredentialProviderError, ECIPlatformError)
    assert issubclass(AnalysisFailedError, ECIPlatformError)
    assert issubclass(AnalysisNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorAccountNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorAccountInvalidRequestError, ECIPlatformError)
    assert issubclass(ConnectorAccountConflictError, ECIPlatformError)
    assert issubclass(MailboxAuthorizationSessionInvalidError, ECIPlatformError)
    assert issubclass(MailboxOAuthAuthorizationDeniedError, ECIPlatformError)
    assert issubclass(MailboxOAuthAuthorizationFailedError, ECIPlatformError)
    assert issubclass(UnsupportedMailboxAuthorizationProviderError, ECIPlatformError)
    assert issubclass(WorkflowActionNotFoundError, ECIPlatformError)
    assert issubclass(WorkflowActionConflictError, ECIPlatformError)
    assert issubclass(AnalysisHasNoDraftReplyError, ECIPlatformError)
    assert issubclass(WorkflowActionNotExecutableError, ECIPlatformError)
    assert issubclass(ConnectedMailboxNotAvailableError, ECIPlatformError)
    assert issubclass(MailboxMessageNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorError, ECIPlatformError)
    assert issubclass(ConnectorAuthenticationError, ConnectorError)
    assert issubclass(ConnectorPermissionError, ConnectorError)
    assert issubclass(ConnectorRateLimitError, ConnectorError)
    assert issubclass(ConnectorUnavailableError, ConnectorError)
    assert issubclass(ConnectorMessageNotFoundError, ConnectorError)
    assert issubclass(ConnectorInvalidCursorError, ConnectorError)
    assert issubclass(ConnectorMessageContentError, ConnectorError)


def test_analysis_not_found_has_generic_message() -> None:
    """Not-found errors must not distinguish unknown from cross-user."""
    error = AnalysisNotFoundError()
    assert error.message == "Analysis not found."
    assert str(error) == "Analysis not found."


def test_connector_account_not_found_has_generic_message() -> None:
    """Not-found errors must not distinguish unknown from cross-user."""
    error = ConnectorAccountNotFoundError()
    assert error.message == "Connector account not found."
    assert str(error) == "Connector account not found."
    assert ConnectorAccountInvalidRequestError().message == (
        "Connector account request is invalid."
    )
    assert ConnectorAccountConflictError().message == "Connector account cannot be updated."
    assert ConnectedMailboxNotAvailableError().message == "Connected mailbox is not available."
    assert MailboxMessageNotFoundError().message == "Mailbox message not found."
    assert "disconnected" not in ConnectedMailboxNotAvailableError().message.lower()
    assert "credential_ref" not in repr(ConnectedMailboxNotAvailableError())
    assert "token" not in MailboxMessageNotFoundError().message.lower()


def test_mailbox_authorization_errors_are_generic() -> None:
    """State failures must not include state, user, or verifier material."""
    invalid = MailboxAuthorizationSessionInvalidError()
    unsupported = UnsupportedMailboxAuthorizationProviderError()
    denied = MailboxOAuthAuthorizationDeniedError()
    failed = MailboxOAuthAuthorizationFailedError()
    assert invalid.message == "Mailbox authorization session is invalid."
    assert unsupported.message == "Mailbox authorization provider is not supported."
    assert denied.message == "Mailbox authorization was denied."
    assert failed.message == "Mailbox authorization failed."
    for text in (
        invalid.message,
        unsupported.message,
        denied.message,
        failed.message,
        str(invalid),
        str(unsupported),
        str(denied),
        str(failed),
    ):
        assert "state" not in text.lower() or "session" in text.lower()
        assert "user_id" not in text
        assert "pkce" not in text.lower()
        assert "verifier" not in text.lower()
        assert "gmail" not in text.lower()
        assert "refresh" not in text.lower()
        assert "token" not in text.lower()


def test_workflow_action_errors_have_generic_messages() -> None:
    """Workflow persistence errors must not distinguish unknown from cross-user."""
    assert WorkflowActionNotFoundError().message == "Workflow action not found."
    assert str(WorkflowActionNotFoundError()) == "Workflow action not found."
    assert WorkflowActionConflictError().message == "Workflow action was updated concurrently."
    assert AnalysisHasNoDraftReplyError().message == "Analysis has no usable draft reply."
    assert WorkflowActionNotExecutableError().message == "Workflow action is not executable."
    assert "connector" not in WorkflowActionNotExecutableError().message.lower()


def test_exception_message_is_preserved() -> None:
    """Exception message should be available on the instance."""
    error = ConfigurationError("invalid configuration")
    assert error.message == "invalid configuration"
    assert str(error) == "invalid configuration"


def test_connector_errors_use_generic_messages() -> None:
    """Connector failures must not leak vendor or network exception text."""
    assert ConnectorAuthenticationError().message == "Connector authentication failed."
    assert ConnectorPermissionError().message == "Connector permission denied."
    assert ConnectorRateLimitError().message == "Connector rate limit exceeded."
    assert ConnectorUnavailableError().message == "Connector is currently unavailable."
    assert ConnectorMessageNotFoundError().message == "Connector message not found."
    assert ConnectorInvalidCursorError().message == "Connector cursor is invalid."
    assert ConnectorMessageContentError().message == "Connector message content is invalid."
    for error in (
        ConnectorAuthenticationError(),
        ConnectorPermissionError(),
        ConnectorRateLimitError(),
        ConnectorUnavailableError(),
        ConnectorMessageNotFoundError(),
        ConnectorInvalidCursorError(),
        ConnectorMessageContentError(),
    ):
        lowered = error.message.lower()
        assert "gmail" not in lowered
        assert "google" not in lowered
        assert "graph" not in lowered
        assert "httpx" not in lowered


def test_communication_action_execution_error_has_generic_message() -> None:
    """Executor failures must not leak provider payload or exception text."""
    error = CommunicationActionExecutionError()
    assert error.message == "Communication action execution failed."
    assert str(error) == "Communication action execution failed."
    lowered = error.message.lower()
    assert "gmail" not in lowered
    assert "graph" not in lowered
    assert "http" not in lowered
    assert "token" not in lowered


def test_communication_credential_errors_have_generic_messages() -> None:
    """Credential failures must not leak locators, tokens, or secret names."""
    unavailable = CommunicationCredentialUnavailableError()
    unsupported = UnsupportedCommunicationCredentialProviderError()
    reauthorization = CommunicationCredentialReauthorizationRequiredError()
    conflict = CommunicationCredentialConflictError()
    assert unavailable.message == "Communication credential is unavailable."
    assert str(unavailable) == "Communication credential is unavailable."
    assert reauthorization.message == "Communication credential is unavailable."
    assert unsupported.message == "Communication credential provider is not supported."
    assert str(unsupported) == "Communication credential provider is not supported."
    assert conflict.message == "Communication credential could not be stored."
    for error in (unavailable, unsupported, reauthorization, conflict):
        lowered = error.message.lower()
        assert "gmail" not in lowered
        assert "graph" not in lowered
        assert "token" not in lowered
        assert "environ" not in lowered
        assert "secret" not in lowered
        assert "credential_ref" not in lowered
        assert "key vault" not in lowered
        assert "secrets manager" not in lowered
        assert "refresh_token" not in lowered


def test_invalid_workflow_transition_has_generic_message() -> None:
    """Illegal workflow transitions must not expose internal from/to status text."""
    error = InvalidWorkflowTransitionError()
    assert error.message == "Invalid workflow state transition."
    assert str(error) == "Invalid workflow state transition."
    assert "pending" not in error.message.lower()
    assert "approved" not in error.message.lower()
