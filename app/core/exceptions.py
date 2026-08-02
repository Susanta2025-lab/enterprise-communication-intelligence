"""Framework-independent application exceptions."""


class ContextMeshError(Exception):
    """Base error for all ContextMesh application failures."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ConfigurationError(ContextMeshError):
    """Raised when application configuration is invalid or incomplete."""


class ServiceUnavailableError(ContextMeshError):
    """Raised when a required service dependency is unavailable."""
