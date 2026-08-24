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


class CommunicationActionExecutionError(ECIPlatformError):
    """Raised when an authorized communication action cannot be executed."""

    def __init__(self, message: str = "Communication action execution failed.") -> None:
        super().__init__(message)


class CommunicationCredentialUnavailableError(ECIPlatformError):
    """Raised when mailbox credential material cannot be resolved."""

    def __init__(self, message: str = "Communication credential is unavailable.") -> None:
        super().__init__(message)


class CommunicationCredentialReauthorizationRequiredError(
    CommunicationCredentialUnavailableError
):
    """Raised when stored refreshable credential material is permanently unusable.

    Compatible with existing unavailable execution semantics at the resolver.
    Token resolution does not mutate ConnectorAccount. Application execution
    maps this signal onto ``REAUTH_REQUIRED`` for the exact owned account
    after TX1, before provider message HTTP.
    """


class CommunicationCredentialConflictError(ECIPlatformError):
    """Raised when a credential locator already exists and must not be overwritten."""

    def __init__(self, message: str = "Communication credential could not be stored.") -> None:
        super().__init__(message)


class MailboxOAuthAuthorizationFailedError(ECIPlatformError):
    """Raised when mailbox authorization cannot be completed.

    Covers invalid identity assertions, missing refresh material, missing
    required grants, and other sanitized provider-exchange failures.
    """

    def __init__(self, message: str = "Mailbox authorization failed.") -> None:
        super().__init__(message)


class UnsupportedCommunicationCredentialProviderError(ECIPlatformError):
    """Raised when credential resolution is requested for an unsupported provider."""

    def __init__(
        self,
        message: str = "Communication credential provider is not supported.",
    ) -> None:
        super().__init__(message)


class CommunicationConnectorNotAvailableError(ECIPlatformError):
    """Raised when a read connector cannot be constructed from account routing data.

    Covers unsupported providers and missing or unusable credential locators at
    the factory boundary. Ownership, ACTIVE status, and ``mail.read`` remain
    application policy. The public message does not distinguish those cases
    and must not include locators or vendor adapter names.
    """

    def __init__(self, message: str = "Communication connector is not available.") -> None:
        super().__init__(message)


class ConnectorError(ECIPlatformError):
    """Raised when a communication connector operation fails."""


class ConnectorAuthenticationError(ConnectorError):
    """Raised when connector credentials are missing or rejected."""

    def __init__(self, message: str = "Connector authentication failed.") -> None:
        super().__init__(message)


class ConnectorPermissionError(ConnectorError):
    """Raised when the connector account lacks permission for the operation."""

    def __init__(self, message: str = "Connector permission denied.") -> None:
        super().__init__(message)


class ConnectorRateLimitError(ConnectorError):
    """Raised when the remote connector throttles the caller."""

    def __init__(self, message: str = "Connector rate limit exceeded.") -> None:
        super().__init__(message)


class ConnectorUnavailableError(ConnectorError):
    """Raised when the remote connector cannot be reached."""

    def __init__(self, message: str = "Connector is currently unavailable.") -> None:
        super().__init__(message)


class ConnectorMessageNotFoundError(ConnectorError):
    """Raised when the requested provider message id is unknown."""

    def __init__(self, message: str = "Connector message not found.") -> None:
        super().__init__(message)


class ConnectorInvalidCursorError(ConnectorError):
    """Raised when a list continuation token cannot be interpreted."""

    def __init__(self, message: str = "Connector cursor is invalid.") -> None:
        super().__init__(message)


class ConnectorMessageContentError(ConnectorError):
    """Raised when a fetched message cannot be normalized into domain form."""

    def __init__(self, message: str = "Connector message content is invalid.") -> None:
        super().__init__(message)
