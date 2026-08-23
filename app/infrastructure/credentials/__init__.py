"""Mailbox credential resolution. Secret stores stay inside implementations."""

from app.infrastructure.credentials.composite import (
    CompositeCommunicationCredentialResolver,
)
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.credentials.locators import (
    create_communication_credential,
    generate_credential_locator,
    is_oauth_credential_locator,
)
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.credentials.oauth import (
    OAuthCommunicationCredentialResolver,
    build_oauth_communication_credential_resolver,
)
from app.infrastructure.credentials.refresh import (
    RefreshableCredentialAdapter,
    RefreshableCredentialResult,
)

__all__ = [
    "CompositeCommunicationCredentialResolver",
    "EnvironmentCommunicationCredentialResolver",
    "InMemoryCommunicationCredentialStore",
    "OAuthCommunicationCredentialResolver",
    "RefreshableCredentialAdapter",
    "RefreshableCredentialResult",
    "build_oauth_communication_credential_resolver",
    "create_communication_credential",
    "generate_credential_locator",
    "is_oauth_credential_locator",
]
