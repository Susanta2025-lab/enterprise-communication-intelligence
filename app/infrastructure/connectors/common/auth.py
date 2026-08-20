"""In-memory access-token injection helpers for connector adapters."""

from collections.abc import Callable

from app.core.exceptions import ConnectorAuthenticationError

AccessTokenProvider = Callable[[], str]


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
