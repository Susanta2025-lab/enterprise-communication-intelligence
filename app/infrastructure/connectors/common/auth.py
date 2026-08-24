"""In-memory access-token injection helpers for connector adapters."""

from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ConnectorAuthenticationError,
    ConnectorUnavailableError,
)
from app.domain.interfaces.communication_credential_resolver import AccessTokenProvider

__all__ = ["AccessTokenProvider", "resolve_access_token"]


def resolve_access_token(provider: AccessTokenProvider) -> str:
    """Return the current bearer token without persisting or logging it.

    Confirmed permanent refresh failure stays
    ``CommunicationCredentialReauthorizationRequiredError``. Transient store
    or refresh failure stays ``CommunicationCredentialUnavailableError``.
    Empty tokens remain authentication failures. Unknown callable failures
    become connector unavailability. Mailbox HTTP is not performed here.
    """
    try:
        token = provider()
    except CommunicationCredentialReauthorizationRequiredError:
        raise
    except CommunicationCredentialUnavailableError:
        raise
    except ConnectorAuthenticationError:
        raise
    except Exception:
        raise ConnectorUnavailableError() from None
    if not isinstance(token, str) or not token.strip():
        raise ConnectorAuthenticationError()
    return token.strip()
