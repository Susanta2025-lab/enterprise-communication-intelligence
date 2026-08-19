"""Framework-independent application exceptions."""


class ECIPlatformError(Exception):
    """Base error for all ECI Platform application failures."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ConfigurationError(ECIPlatformError):
    """Raised when application configuration is invalid or incomplete."""


class ServiceUnavailableError(ECIPlatformError):
    """Raised when a required service dependency is unavailable."""


class PersistenceError(ECIPlatformError):
    """Raised when a persistence operation fails without a more specific type."""
