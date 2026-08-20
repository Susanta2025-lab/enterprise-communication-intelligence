"""Unit tests for HTML-to-plain-text conversion used by the Gmail adapter."""

import pytest

from app.core.exceptions import ConnectorMessageContentError
from app.infrastructure.connectors.common.html_text import html_to_plain_text
from tests.unit.infrastructure.connectors.gmail.conftest import b64url, gmail_resource, header


def test_html_safety_drops_script_style_and_tags() -> None:
    html = (
        "<script>secretExecutable()</script>"
        "<style>body { color: red; }</style>"
        "<p>Hello <b>world</b></p>"
    )

    text = html_to_plain_text(html)

    assert "Hello world" in text
    assert "secretExecutable()" not in text
    assert "color: red" not in text
    assert "<p>" not in text
    assert "<b>" not in text
    assert "<script>" not in text
    assert "<style>" not in text


def test_html_only_gmail_message_uses_safe_plain_text(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    html = (
        "<script>secretExecutable()</script>"
        "<style>body { color: red; }</style>"
        "<p>Hello <b>world</b></p>"
    )
    payload = {
        "mimeType": "text/html",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
        ],
        "body": {"data": b64url(html)},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert "Hello world" in message.body
    assert "secretExecutable()" not in message.body
    assert "color: red" not in message.body
    assert "<p>" not in message.body
    assert "<b>" not in message.body


def test_html_entities_are_decoded() -> None:
    assert html_to_plain_text("<p>Tom &amp; Jerry</p>") == "Tom & Jerry"


def test_unclosed_html_does_not_crash() -> None:
    assert html_to_plain_text("<p>Hello") == "Hello"


def test_script_only_html_is_content_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/html",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
        ],
        "body": {
            "data": b64url("<script>secretExecutable()</script><style>body{}</style>")
        },
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")
