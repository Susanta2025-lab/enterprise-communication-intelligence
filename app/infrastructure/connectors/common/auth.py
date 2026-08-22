"""In-memory access-token injection helpers for connector adapters."""

from app.core.exceptions import ConnectorAuthenticationError
from app.domain.interfaces.communication_credential_resolver import AccessTokenProvider

__all__ = ["AccessTokenProvider", "resolve_access_token"]


def resolve_access_token(provider: AccessTokenProvider) -> str:
    """Return the current bearer token without persisting or logging it.

    The callable may later wrap OAuth refresh or secret lookup. This helper
    only validates that a non-empty in-memory token is available.
    """
    try:
        token = provider()
    except ConnectorAuthenticationError:
        raise
    except Exception:
        raise ConnectorAuthenticationError() from None
    if not isinstance(token, str) or not token.strip():
        raise ConnectorAuthenticationError()
    return token.strip()
