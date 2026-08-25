"""Unit tests for mailbox OAuth frontend return helpers."""

from urllib.parse import parse_qs, urlparse

from app.api.oauth_frontend_return import (
    build_oauth_return_location,
    classify_oauth_callback_failure,
)
from app.application.exceptions import (
    MailboxAuthorizationSessionInvalidError,
    MailboxOAuthAuthorizationDeniedError,
)
from app.core.exceptions import (
    MailboxOAuthAuthorizationFailedError,
    MailboxOAuthIdentityMismatchError,
)


def test_build_oauth_return_location_only_allowlisted_query() -> None:
    location = build_oauth_return_location(
        "http://localhost:5173",
        oauth="success",
        provider="gmail",
    )
    parsed = urlparse(location)
    assert parsed.netloc == "localhost:5173"
    assert parse_qs(parsed.query) == {"oauth": ["success"], "provider": ["gmail"]}
    assert parsed.fragment == ""


def test_build_oauth_return_location_rejects_unknown_values() -> None:
    location = build_oauth_return_location(
        "https://eci.example.invalid/app",
        oauth="not-a-real-outcome",
        provider="not-a-provider",
    )
    parsed = urlparse(location)
    assert parsed.path == "/app"
    assert parse_qs(parsed.query) == {"oauth": ["failed"], "provider": ["gmail"]}


def test_classify_oauth_callback_failure_uses_stable_categories() -> None:
    assert classify_oauth_callback_failure(MailboxOAuthIdentityMismatchError()) == (
        "identity_mismatch"
    )
    assert classify_oauth_callback_failure(MailboxOAuthAuthorizationDeniedError()) == "denied"
    assert classify_oauth_callback_failure(MailboxAuthorizationSessionInvalidError()) == "expired"
    assert classify_oauth_callback_failure(MailboxOAuthAuthorizationFailedError()) == "failed"
    assert classify_oauth_callback_failure(RuntimeError("provider boom")) == "failed"
