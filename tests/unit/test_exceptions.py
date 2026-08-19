"""Unit tests for application exceptions."""

from app.application.exceptions import AnalysisFailedError, AnalysisNotFoundError
from app.core.exceptions import (
    ConfigurationError,
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


def test_analysis_not_found_has_generic_message() -> None:
    """Not-found errors must not distinguish unknown from cross-user."""
    error = AnalysisNotFoundError()
    assert error.message == "Analysis not found."
    assert str(error) == "Analysis not found."


def test_exception_message_is_preserved() -> None:
    """Exception message should be available on the instance."""
    error = ConfigurationError("invalid configuration")
    assert error.message == "invalid configuration"
    assert str(error) == "invalid configuration"
