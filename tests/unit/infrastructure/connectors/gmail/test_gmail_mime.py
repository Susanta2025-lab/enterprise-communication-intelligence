"""Unit tests for Gmail MIME traversal and body decoding."""

import base64

import pytest

from app.core.exceptions import ConnectorMessageContentError
from tests.unit.infrastructure.connectors.gmail.conftest import (
    b64url,
    gmail_resource,
    header,
    text_part,
)


def test_root_text_plain_body(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1", body="Plain root body")

    message = connector.fetch_message("msg-1")

    assert message.body == "Plain root body"


def test_multipart_alternative_prefers_plain_over_html(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/alternative",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Subject", "Alt"),
        ],
        "parts": [
            text_part("Choose the plain text"),
            text_part("<p>HTML should lose</p>", mime_type="text/html"),
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Choose the plain text"
    assert "HTML should lose" not in message.body


def test_html_before_plain_still_prefers_plain(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/alternative",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
        ],
        "parts": [
            text_part("<p>HTML encountered first</p>", mime_type="text/html"),
            text_part("Plain must still win"),
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Plain must still win"
    assert "HTML encountered first" not in message.body


def test_first_plain_part_is_used_without_concatenation(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
        ],
        "parts": [
            text_part("First plain body"),
            text_part("Second unrelated plain body"),
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "First plain body"
    assert "Second unrelated plain body" not in message.body


def test_html_only_converts_to_plain_text(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/html",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Content-Type", "text/html; charset=utf-8"),
        ],
        "body": {"data": b64url("<p>Hello <b>team</b></p>")},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Hello team"
    assert "<p>" not in message.body
    assert "<b>" not in message.body


def test_nested_multipart_mixed_extracts_nested_text(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
        ],
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "filename": "",
                "headers": [],
                "parts": [
                    text_part("Nested plain body"),
                    text_part("<p>Nested html</p>", mime_type="text/html"),
                ],
            },
            text_part(
                "attachment-bytes",
                mime_type="application/pdf",
                filename="report.pdf",
            ),
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Nested plain body"
    assert "attachment-bytes" not in message.body


def test_content_disposition_attachment_is_ignored(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [header("From", "alice@example.com"), header("To", "bob@example.com")],
        "parts": [
            text_part("Visible body"),
            text_part(
                "SECRET-DISPOSITION-ATTACHMENT",
                mime_type="text/plain",
                filename="",
                headers=[header("Content-Disposition", "attachment")],
            ),
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Visible body"
    assert "SECRET-DISPOSITION-ATTACHMENT" not in message.body


def test_inline_disposition_is_not_treated_as_attachment(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Content-Disposition", "inline"),
        ],
        "body": {"data": b64url("Inline body kept")},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Inline body kept"


def test_filename_attachment_is_ignored(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [header("From", "alice@example.com"), header("To", "bob@example.com")],
        "parts": [
            text_part("Visible body"),
            text_part("SECRET-ATTACHMENT", mime_type="text/plain", filename="notes.txt"),
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Visible body"
    assert "SECRET-ATTACHMENT" not in message.body
    assert not any("attachments" in str(request.url) for request in stub.requests)


def test_attachment_id_only_part_is_ignored(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [header("From", "alice@example.com"), header("To", "bob@example.com")],
        "parts": [
            text_part("Keep this body"),
            {
                "mimeType": "application/pdf",
                "filename": "",
                "headers": [],
                "body": {"attachmentId": "ANGjdJ-secret", "size": 2048},
            },
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Keep this body"
    assert len(stub.requests) == 1
    assert "attachments" not in str(stub.requests[0].url)


def test_missing_base64_padding_still_decodes(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    encoded = b64url("Padding needed here")
    assert len(encoded) % 4 != 0
    stub.messages["msg-1"] = gmail_resource("msg-1")
    stub.messages["msg-1"]["payload"]["body"]["data"] = encoded

    message = connector.fetch_message("msg-1")

    assert message.body == "Padding needed here"


def test_malformed_base64_raises_content_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1")
    stub.messages["msg-1"]["payload"]["body"]["data"] = "!!!not-base64!!!"

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    assert exc_info.value.message == "Connector message content is invalid."
    assert "!!!not-base64!!!" not in exc_info.value.message
    assert exc_info.value.__cause__ is None


def test_utf8_body_round_trip(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1", body="Café résumé — 你好")

    message = connector.fetch_message("msg-1")

    assert message.body == "Café résumé — 你好"


def test_quoted_latin1_charset_is_used(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Content-Type", 'text/plain; charset="iso-8859-1"'),
        ],
        "body": {
            "data": base64.urlsafe_b64encode("Café".encode("iso-8859-1")).decode().rstrip("=")
        },
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Café"


def test_declared_latin1_charset_is_used(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Content-Type", "text/plain; charset=iso-8859-1"),
        ],
        "body": {
            "data": base64.urlsafe_b64encode("Café".encode("iso-8859-1")).decode().rstrip("=")
        },
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Café"


def test_empty_textual_body_raises_content_error(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [header("From", "alice@example.com"), header("To", "bob@example.com")],
        "body": {"data": b64url("   ")},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload, snippet="partial snippet")

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    assert "partial snippet" not in exc_info.value.message


def test_unknown_charset_falls_back_without_crashing(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Content-Type", "text/plain; charset=not-a-real-charset"),
        ],
        "body": {"data": b64url("Fallback utf-8 body")},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.body == "Fallback utf-8 body"


def test_snippet_is_not_used_as_body_fallback(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [header("From", "alice@example.com"), header("To", "bob@example.com")],
        "parts": [
            text_part("ignored", filename="file.bin", mime_type="application/octet-stream"),
        ],
    }
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=payload,
        snippet="Do not analyze this snippet",
    )

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")
