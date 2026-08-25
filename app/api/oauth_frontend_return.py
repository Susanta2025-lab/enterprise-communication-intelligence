"""Fixed frontend return after mailbox OAuth callbacks.

The return location is server-configured. Callback query input never chooses
the redirect target. Authorization codes, state, and tokens are never added.
"""

from urllib.parse import urlencode, urlparse, urlunparse

from fastapi.responses import RedirectResponse

from app.application.exceptions import (
    ConnectorAccountConflictError,
    MailboxAuthorizationSessionInvalidError,
    MailboxOAuthAuthorizationDeniedError,
)
from app.core.config import get_settings
from app.core.exceptions import (
    MailboxOAuthAuthorizationFailedError,
    MailboxOAuthIdentityMismatchError,
    ServiceUnavailableError,
)

_OAUTH_OUTCOMES = frozenset({"success", "denied", "expired", "identity_mismatch", "failed"})
_OAUTH_PROVIDERS = frozenset({"gmail", "microsoft_graph"})
_CALLBACK_FAILURE_TYPES = (
    MailboxOAuthAuthorizationDeniedError,
    MailboxAuthorizationSessionInvalidError,
    MailboxOAuthAuthorizationFailedError,
    ConnectorAccountConflictError,
    ServiceUnavailableError,
)


def is_oauth_callback_failure(exc: BaseException) -> bool:
    """Return True when the callback exception may be mapped to a sanitized return."""
    return isinstance(exc, _CALLBACK_FAILURE_TYPES)


def classify_oauth_callback_failure(exc: BaseException) -> str:
    """Map a callback exception onto a stable product failure category."""
    if isinstance(exc, MailboxOAuthIdentityMismatchError):
        return "identity_mismatch"
    if isinstance(exc, MailboxOAuthAuthorizationDeniedError):
        return "denied"
    if isinstance(exc, MailboxAuthorizationSessionInvalidError):
        return "expired"
    return "failed"


def maybe_oauth_frontend_redirect(*, provider: str, oauth: str) -> RedirectResponse | None:
    """Return a 302 to the configured frontend URL, or None for JSON callbacks."""
    base = get_settings().frontend_oauth_return_url
    if base is None:
        return None
    location = build_oauth_return_location(base, oauth=oauth, provider=provider)
    return RedirectResponse(url=location, status_code=302)


def build_oauth_return_location(base: str, *, oauth: str, provider: str) -> str:
    """Append only allowlisted oauth and provider query values."""
    outcome = oauth if oauth in _OAUTH_OUTCOMES else "failed"
    provider_slug = provider if provider in _OAUTH_PROVIDERS else "gmail"
    parsed = urlparse(base)
    query = urlencode({"oauth": outcome, "provider": provider_slug})
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, ""))
