"""HTTP mapping and privacy tests for mailbox-read application errors."""

from fastapi.testclient import TestClient

from app.application.exceptions import (
    ConnectedMailboxNotAvailableError,
    MailboxMessageNotFoundError,
    MailboxPaginationCursorInvalidError,
)
from app.core.exceptions import ECIPlatformError
from app.main import create_app

_SECRET_MARKERS = (
    "credential_ref",
    "oauth-secret-locator",
    "refresh_token",
    "access_token",
    "ya29.",
    "nextLink",
    "https://graph.microsoft.com",
)


def test_mailbox_errors_are_sanitized_application_errors() -> None:
    """New mailbox-read errors expose only generic public messages."""
    unavailable = ConnectedMailboxNotAvailableError()
    missing = MailboxMessageNotFoundError()
    invalid_cursor = MailboxPaginationCursorInvalidError()
    assert issubclass(ConnectedMailboxNotAvailableError, ECIPlatformError)
    assert issubclass(MailboxMessageNotFoundError, ECIPlatformError)
    assert issubclass(MailboxPaginationCursorInvalidError, ECIPlatformError)
    assert unavailable.message == "Connected mailbox is not available."
    assert str(unavailable) == "Connected mailbox is not available."
    assert missing.message == "Mailbox message not found."
    assert str(missing) == "Mailbox message not found."
    assert invalid_cursor.message == "Mailbox pagination cursor is invalid."
    assert str(invalid_cursor) == "Mailbox pagination cursor is invalid."
    for text in (
        unavailable.message,
        str(unavailable),
        repr(unavailable),
        missing.message,
        str(missing),
        repr(missing),
        invalid_cursor.message,
        str(invalid_cursor),
        repr(invalid_cursor),
    ):
        lowered = text.lower()
        assert "credential_ref" not in lowered
        assert "token" not in lowered
        assert "disconnected" not in lowered
        assert "reauth" not in lowered
        assert "mail.read" not in lowered
        assert "gmail" not in lowered
        assert "graph" not in lowered


def test_connected_mailbox_not_available_maps_to_sanitized_409() -> None:
    """Owned-but-unusable mailbox failures are 409 without internal distinctions."""
    application = create_app()

    @application.get("/__phase14a/mailbox-unavailable")
    def _unavailable() -> None:
        raise ConnectedMailboxNotAvailableError()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/__phase14a/mailbox-unavailable")

    assert response.status_code == 409
    assert response.json() == {"detail": "Connected mailbox is not available."}
    serialized = repr(response.json())
    for marker in _SECRET_MARKERS:
        assert marker not in serialized


def test_mailbox_message_not_found_maps_to_sanitized_404() -> None:
    """Unknown provider messages are indistinguishable 404 resources."""
    application = create_app()

    @application.get("/__phase14a/mailbox-message-missing")
    def _missing() -> None:
        raise MailboxMessageNotFoundError()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/__phase14a/mailbox-message-missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Mailbox message not found."}
    serialized = repr(response.json())
    for marker in _SECRET_MARKERS:
        assert marker not in serialized


def test_mailbox_pagination_cursor_invalid_maps_to_sanitized_400() -> None:
    """Invalid list cursors are 400 without provider pagination URLs."""
    application = create_app()

    @application.get("/__phase14d/mailbox-cursor-invalid")
    def _invalid() -> None:
        raise MailboxPaginationCursorInvalidError()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/__phase14d/mailbox-cursor-invalid")

    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox pagination cursor is invalid."}
    serialized = repr(response.json())
    for marker in _SECRET_MARKERS:
        assert marker not in serialized
