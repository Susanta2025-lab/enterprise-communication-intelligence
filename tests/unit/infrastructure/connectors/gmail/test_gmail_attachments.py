"""Gmail attachment metadata contracts. Listing and fetch must not download bytes."""

import pytest

from app.core.exceptions import (
    ConnectorAttachmentContentError,
    ConnectorAttachmentMetadataError,
    ConnectorAttachmentNotFoundError,
    ConnectorMessageNotFoundError,
)
from app.domain.enums import AttachmentDisposition
from app.domain.interfaces import ConnectorMessageQuery
from app.infrastructure.connectors.gmail.connector import attachment_metadata_fields
from tests.unit.infrastructure.connectors.gmail.conftest import (
    GMAIL_API_PREFIX,
    attachment_part,
    filename_data_part_without_attachment_id,
    gmail_resource,
    header,
    text_part,
)


def _b64url_bytes(payload: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _mixed_payload(*parts: object) -> dict:
    return {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("To", "bob@example.com"),
            header("Subject", "With attachments"),
        ],
        "parts": list(parts),
    }


def _assert_no_explicit_attachment_content_request(stub) -> None:
    """A: ECI must not call users.messages.attachments.get."""
    assert stub.attachment_content_requests == []
    for request in stub.requests:
        path = request.url.path.lower()
        assert "/attachments" not in path
        assert "attachments.get" not in str(request.url).lower()


def _assert_list_attachments_omits_body_data(request) -> None:
    """list_attachments requests metadata fields and never selects body.data."""
    fields = request.url.params.get("fields")
    assert fields is not None
    assert fields == attachment_metadata_fields()
    assert "data" not in fields
    assert "body.data" not in fields
    assert "body(size,attachmentId)" in fields
    assert "filename" in fields
    assert "mimeType" in fields
    assert "headers(name,value)" in fields
    assert "parts(" in fields
    assert request.url.params.get("format") == "full"


def test_list_messages_does_not_download_attachment_content(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="ANGjdJ-secret", include_data=True),
        ),
    )

    page = connector.list_messages(ConnectorMessageQuery(limit=1))

    assert page.items[0].body == "Visible body"
    assert "must-not-decode" not in page.items[0].body
    _assert_no_explicit_attachment_content_request(stub)
    fetch_requests = [request for request in stub.requests if request.url.path.endswith("/msg-1")]
    assert fetch_requests
    assert all(request.url.params.get("fields") is None for request in fetch_requests)


def test_fetch_message_does_not_download_attachment_content(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Keep this body"),
            attachment_part(attachment_id="ANGjdJ-secret", include_data=True),
        ),
    )

    message = connector.fetch_message("msg-1")

    assert message.body == "Keep this body"
    assert len(stub.requests) == 1
    assert stub.requests[0].url.path == f"{GMAIL_API_PREFIX}/msg-1"
    assert stub.requests[0].url.params.get("format") == "full"
    assert stub.requests[0].url.params.get("fields") is None
    _assert_no_explicit_attachment_content_request(stub)


def test_list_attachments_uses_format_full_without_content_endpoint(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(
                attachment_id="att-pdf-1",
                filename="report.pdf",
                mime_type="application/pdf",
                size=4096,
            ),
        ),
    )

    page = connector.list_attachments("msg-1")

    assert len(page.items) == 1
    assert page.truncated is False
    item = page.items[0]
    assert item.provider_attachment_id == "att-pdf-1"
    assert item.filename == "report.pdf"
    assert item.media_type == "application/pdf"
    assert item.reported_size == 4096
    assert item.disposition is AttachmentDisposition.ATTACHMENT
    assert item.is_inline is False
    assert len(stub.requests) == 1
    assert stub.requests[0].url.path == f"{GMAIL_API_PREFIX}/msg-1"
    _assert_list_attachments_omits_body_data(stub.requests[0])
    _assert_no_explicit_attachment_content_request(stub)


def test_list_attachments_belongs_to_selected_message(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-a"] = gmail_resource(
        "msg-a",
        payload=_mixed_payload(
            text_part("Body A"),
            attachment_part(attachment_id="att-a", filename="a.pdf"),
        ),
    )
    stub.messages["msg-b"] = gmail_resource(
        "msg-b",
        payload=_mixed_payload(
            text_part("Body B"),
            attachment_part(attachment_id="att-b", filename="b.pdf"),
        ),
    )

    page = connector.list_attachments("msg-b")

    assert [item.provider_attachment_id for item in page.items] == ["att-b"]
    assert page.items[0].filename == "b.pdf"
    assert all(request.url.path.endswith("/msg-b") for request in stub.requests)
    _assert_no_explicit_attachment_content_request(stub)


def test_nested_multipart_collects_every_qualifying_part(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "headers": [header("From", "alice@example.com"), header("To", "bob@example.com")],
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
            attachment_part(attachment_id="att-outer", filename="outer.pdf"),
            {
                "mimeType": "multipart/related",
                "filename": "",
                "headers": [],
                "parts": [
                    text_part("Related text"),
                    attachment_part(
                        attachment_id="att-inline",
                        filename="logo.png",
                        mime_type="image/png",
                        disposition="inline",
                        content_id="<logo@example>",
                    ),
                ],
            },
        ],
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    page = connector.list_attachments("msg-1")
    message = connector.fetch_message("msg-1")

    assert [item.provider_attachment_id for item in page.items] == ["att-outer", "att-inline"]
    inline = page.items[1]
    assert inline.is_inline is True
    assert inline.disposition is AttachmentDisposition.INLINE
    assert inline.content_id == "logo@example"
    assert message.body == "Nested plain body"
    _assert_no_explicit_attachment_content_request(stub)


def test_filename_from_content_disposition_when_part_filename_empty(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(
                attachment_id="att-disp",
                filename="",
                disposition='attachment; filename="from-header.xlsx"',
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
    )

    page = connector.list_attachments("msg-1")

    assert page.items[0].filename == "from-header.xlsx"
    _assert_no_explicit_attachment_content_request(stub)


def test_filename_body_data_without_attachment_id_is_not_retrievable(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    secret = "SECRET-INLINE-PART-DATA"
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            filename_data_part_without_attachment_id(secret),
        ),
    )

    message = connector.fetch_message("msg-1")
    page = connector.list_attachments("msg-1")

    assert message.body == "Visible body"
    assert secret not in message.body
    assert page.items == []
    _assert_no_explicit_attachment_content_request(stub)
    list_request = stub.requests[1]
    _assert_list_attachments_omits_body_data(list_request)
    assert stub.requests[0].url.params.get("fields") is None


def test_missing_attachment_id_is_omitted(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            text_part("SECRET-ATTACHMENT", mime_type="text/plain", filename="notes.txt"),
            attachment_part(attachment_id="att-keep", filename="keep.pdf"),
        ),
    )

    page = connector.list_attachments("msg-1")
    message = connector.fetch_message("msg-1")

    assert [item.provider_attachment_id for item in page.items] == ["att-keep"]
    assert message.body == "Visible body"
    assert "SECRET-ATTACHMENT" not in message.body
    _assert_no_explicit_attachment_content_request(stub)


def test_malformed_size_skips_unusable_part(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    bad = attachment_part(attachment_id="att-bad", filename="bad.pdf")
    bad["body"]["size"] = "huge"
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(text_part("Visible body"), bad),
    )

    page = connector.list_attachments("msg-1")

    assert page.items == []
    _assert_no_explicit_attachment_content_request(stub)


def test_duplicate_attachment_ids_fail_closed(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="dup-id", filename="one.pdf"),
            attachment_part(attachment_id="dup-id", filename="two.pdf"),
        ),
    )

    with pytest.raises(ConnectorAttachmentMetadataError) as exc_info:
        connector.list_attachments("msg-1")

    assert exc_info.value.message == "Connector attachment metadata is invalid."
    assert "dup-id" not in exc_info.value.message
    assert "two.pdf" not in exc_info.value.message
    _assert_no_explicit_attachment_content_request(stub)


def test_same_filename_does_not_authorize_or_collapse_ids(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="att-1", filename="same.pdf"),
            attachment_part(attachment_id="att-2", filename="same.pdf"),
        ),
    )

    page = connector.list_attachments("msg-1")

    assert [item.provider_attachment_id for item in page.items] == ["att-1", "att-2"]
    assert {item.filename for item in page.items} == {"same.pdf"}
    _assert_no_explicit_attachment_content_request(stub)


def test_list_attachments_unknown_message_is_not_found(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.fetch_status["missing"] = 404

    with pytest.raises(ConnectorMessageNotFoundError):
        connector.list_attachments("missing")

    _assert_no_explicit_attachment_content_request(stub)


def test_blank_attachment_id_does_not_call_content_endpoint(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector

    with pytest.raises(ConnectorAttachmentNotFoundError):
        connector.fetch_attachment_content("msg-1", "   ")

    assert stub.requests == []
    _assert_no_explicit_attachment_content_request(stub)


def test_fetch_attachment_content_uses_one_attachment_endpoint(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(
                attachment_id="att-pdf-1",
                filename="report.pdf",
                mime_type="application/pdf",
                size=len(pdf),
            ),
            attachment_part(attachment_id="att-sibling", filename="other.pdf"),
        ),
    )
    stub.attachment_payloads[("msg-1", "att-pdf-1")] = {
        "size": len(pdf),
        "data": _b64url_bytes(pdf),
        "attachmentId": "att-pdf-1",
    }

    content = connector.fetch_attachment_content("msg-1", "att-pdf-1")

    assert content.content == pdf
    assert content.source_message_id == "msg-1"
    assert content.source_attachment_id == "att-pdf-1"
    assert content.metadata.filename == "report.pdf"
    assert [request.url.path for request in stub.attachment_content_requests] == [
        f"{GMAIL_API_PREFIX}/msg-1/attachments/att-pdf-1"
    ]
    assert stub.requests[0].url.path == f"{GMAIL_API_PREFIX}/msg-1"
    assert stub.requests[0].url.params.get("fields") == attachment_metadata_fields()
    assert "data" not in (stub.requests[0].url.params.get("fields") or "")


def test_fetch_attachment_content_rejects_malformed_base64(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="att-1", size=4),
        ),
    )
    stub.attachment_payloads[("msg-1", "att-1")] = {"size": 4, "data": "not-base64***"}

    with pytest.raises(ConnectorAttachmentContentError) as exc_info:
        connector.fetch_attachment_content("msg-1", "att-1")

    assert exc_info.value.message == "Connector attachment content is invalid."
    assert "not-base64" not in exc_info.value.message


def test_fetch_attachment_content_rejects_oversized_metadata_without_content_get(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="att-huge", size=5 * 1024 * 1024 + 1),
        ),
    )

    with pytest.raises(ConnectorAttachmentContentError):
        connector.fetch_attachment_content("msg-1", "att-huge")

    _assert_no_explicit_attachment_content_request(stub)


def test_fetch_attachment_content_rejects_actual_oversize(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    huge = b"%PDF-" + b"A" * (5 * 1024 * 1024)
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="att-1", size=8),
        ),
    )
    stub.attachment_payloads[("msg-1", "att-1")] = {
        "size": len(huge),
        "data": _b64url_bytes(huge),
    }

    with pytest.raises(ConnectorAttachmentContentError):
        connector.fetch_attachment_content("msg-1", "att-1")


def test_fetch_unknown_attachment_does_not_call_content_endpoint(
    gmail_connector: tuple,
) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        payload=_mixed_payload(
            text_part("Visible body"),
            attachment_part(attachment_id="att-keep"),
        ),
    )

    with pytest.raises(ConnectorAttachmentNotFoundError):
        connector.fetch_attachment_content("msg-1", "att-missing")

    _assert_no_explicit_attachment_content_request(stub)
