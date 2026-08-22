"""Unit tests for application exceptions."""

from app.application.exceptions import (
    AnalysisFailedError,
    AnalysisHasNoDraftReplyError,
    AnalysisNotFoundError,
    ConnectorAccountInvalidRequestError,
    ConnectorAccountNotFoundError,
    WorkflowActionConflictError,
    WorkflowActionNotExecutableError,
    WorkflowActionNotFoundError,
)
from app.core.exceptions import (
    CommunicationActionExecutionError,
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
    PersistenceError,
    ServiceUnavailableError,
)
from app.domain.exceptions import InvalidWorkflowTransitionError


def test_exception_hierarchy() -> None:
    """Application exceptions should share a common base type."""
    assert issubclass(ConfigurationError, ECIPlatformError)
    assert issubclass(ServiceUnavailableError, ECIPlatformError)
    assert issubclass(PersistenceError, ECIPlatformError)
    assert issubclass(CommunicationActionExecutionError, ECIPlatformError)
    assert issubclass(AnalysisFailedError, ECIPlatformError)
    assert issubclass(AnalysisNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorAccountNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorAccountInvalidRequestError, ECIPlatformError)
    assert issubclass(WorkflowActionNotFoundError, ECIPlatformError)
    assert issubclass(WorkflowActionConflictError, ECIPlatformError)
    assert issubclass(AnalysisHasNoDraftReplyError, ECIPlatformError)
    assert issubclass(WorkflowActionNotExecutableError, ECIPlatformError)
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


def test_invalid_workflow_transition_has_generic_message() -> None:
    """Illegal workflow transitions must not expose internal from/to status text."""
    error = InvalidWorkflowTransitionError()
    assert error.message == "Invalid workflow state transition."
    assert str(error) == "Invalid workflow state transition."
    assert "pending" not in error.message.lower()
    assert "approved" not in error.message.lower()
