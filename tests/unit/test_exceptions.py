"""Unit tests for application exceptions."""

from app.core.exceptions import (
    ConfigurationError,
    ECIPlatformError,
    ServiceUnavailableError,
)


def test_exception_hierarchy() -> None:
    """Application exceptions should share a common base type."""
    assert issubclass(ConfigurationError, ECIPlatformError)
    assert issubclass(ServiceUnavailableError, ECIPlatformError)


def test_exception_message_is_preserved() -> None:
    """Exception message should be available on the instance."""
    error = ConfigurationError("invalid configuration")
    assert error.message == "invalid configuration"
    assert str(error) == "invalid configuration"
