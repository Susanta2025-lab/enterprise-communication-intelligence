"""Unit tests for application exceptions."""

from app.application.exceptions import (
    AnalysisFailedError,
    AnalysisNotFoundError,
    ConnectorAccountInvalidRequestError,
    ConnectorAccountNotFoundError,
)
from app.core.exceptions import (
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


def test_exception_hierarchy() -> None:
    """Application exceptions should share a common base type."""
    assert issubclass(ConfigurationError, ECIPlatformError)
    assert issubclass(ServiceUnavailableError, ECIPlatformError)
    assert issubclass(PersistenceError, ECIPlatformError)
    assert issubclass(AnalysisFailedError, ECIPlatformError)
    assert issubclass(AnalysisNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorAccountNotFoundError, ECIPlatformError)
    assert issubclass(ConnectorAccountInvalidRequestError, ECIPlatformError)
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
