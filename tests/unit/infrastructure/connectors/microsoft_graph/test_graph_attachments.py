"""Graph attachment metadata contracts. List/fetch must not retrieve contentBytes."""

import httpx
import pytest

from app.core.exceptions import (
    ConnectorAttachmentContentError,
    ConnectorAttachmentMetadataError,
    ConnectorAttachmentNotFoundError,
    ConnectorMessageNotFoundError,
    ConnectorUnsupportedAttachmentError,
)
from app.domain.enums import AttachmentDisposition
from app.domain.interfaces import ConnectorMessageQuery
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    ATTACHMENT_SELECT_FIELDS,
    GRAPH_API_PREFIX,
    graph_file_attachment,
    graph_resource,
)


def _b64_bytes(payload: bytes) -> str:
    import base64

    return base64.b64encode(payload).decode("ascii")


def _select_fields(request: httpx.Request) -> set[str]:
    return {part.strip() for part in request.url.params.get("$select", "").split(",") if part}


def _assert_metadata_only(stub) -> None:
    assert stub.attachment_content_requests == []
    for request in stub.requests:
        url = str(request.url)
        path = request.url.path
        assert "$value" not in url
        assert "$expand" not in url
        assert "contentBytes" not in url
        assert not path.endswith("/$value")
        if path.rstrip("/").endswith("/attachments"):
            fields = _select_fields(request)
            assert fields == ATTACHMENT_SELECT_FIELDS
            assert "contentBytes" not in fields


def test_list_messages_does_not_retrieve_attachment_content(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-1", extra={"contentBytes": "UEsFBgAAAAA="}),
    ]

    page = connector.list_messages(ConnectorMessageQuery(limit=1))

    assert page.items[0].body.startswith("Please review")
    assert all("/attachments" not in request.url.path for request in stub.requests)
    _assert_metadata_only(stub)


def test_fetch_message_does_not_retrieve_attachment_content(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")
    stub.attachments["msg-1"] = [graph_file_attachment("att-1")]

    message = connector.fetch_message("msg-1")

    assert message.body.startswith("Please review")
    assert len(stub.requests) == 1
    assert "/attachments" not in stub.requests[0].url.path
    fields = _select_fields(stub.requests[0])
    assert "hasAttachments" not in fields
    assert "attachments" not in fields
    _assert_metadata_only(stub)


def test_list_attachments_selects_metadata_without_content_bytes(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment(
            "att-pdf-1",
            name="report.pdf",
            content_type="application/pdf",
            size=4096,
        )
    ]

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
    request = stub.requests[0]
    assert request.method == "GET"
    assert request.url.path == f"{GRAPH_API_PREFIX}/msg-1/attachments"
    assert request.headers.get("prefer") is None
    _assert_metadata_only(stub)


def test_list_attachments_belongs_to_selected_message(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-a"] = [graph_file_attachment("att-a", name="a.pdf")]
    stub.attachments["msg-b"] = [graph_file_attachment("att-b", name="b.pdf")]

    page = connector.list_attachments("msg-b")

    assert [item.provider_attachment_id for item in page.items] == ["att-b"]
    assert all(request.url.path.endswith("/msg-b/attachments") for request in stub.requests)
    _assert_metadata_only(stub)


def test_inline_file_attachment_is_listed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment(
            "att-inline",
            name="logo.png",
            content_type="image/png",
            is_inline=True,
            content_id="logo@example",
        )
    ]

    page = connector.list_attachments("msg-1")

    assert page.items[0].is_inline is True
    assert page.items[0].disposition is AttachmentDisposition.INLINE
    assert page.items[0].content_id == "logo@example"
    _assert_metadata_only(stub)


def test_item_attachment_fails_closed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        {
            "@odata.type": "#microsoft.graph.itemAttachment",
            "id": "att-item",
            "name": "embedded.msg",
            "contentType": "message/rfc822",
            "size": 100,
            "isInline": False,
        }
    ]

    with pytest.raises(ConnectorUnsupportedAttachmentError) as exc_info:
        connector.list_attachments("msg-1")

    assert exc_info.value.message == "Connector attachment is not supported."
    assert "itemAttachment" not in exc_info.value.message
    assert "embedded.msg" not in exc_info.value.message
    _assert_metadata_only(stub)


def test_reference_attachment_fails_closed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        {
            "@odata.type": "#microsoft.graph.referenceAttachment",
            "id": "att-ref",
            "name": "shared.docx",
            "contentType": "application/octet-stream",
            "size": 12,
            "isInline": False,
        }
    ]

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.list_attachments("msg-1")

    _assert_metadata_only(stub)


def test_unknown_odata_type_fails_closed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-1", odata_type="#microsoft.graph.unexpectedAttachment")
    ]

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.list_attachments("msg-1")

    _assert_metadata_only(stub)


def test_mixed_file_and_item_fails_closed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-file"),
        {
            "@odata.type": "#microsoft.graph.itemAttachment",
            "id": "att-item",
            "name": "nested",
            "contentType": "message/rfc822",
            "size": 10,
            "isInline": False,
        },
    ]

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.list_attachments("msg-1")

    _assert_metadata_only(stub)


def test_content_bytes_in_metadata_response_fail_closed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-1", extra={"contentBytes": "UEsFBgAAAAA="})
    ]

    with pytest.raises(ConnectorAttachmentMetadataError) as exc_info:
        connector.list_attachments("msg-1")

    assert exc_info.value.message == "Connector attachment metadata is invalid."
    assert "UEsFBgAAAAA=" not in exc_info.value.message
    _assert_metadata_only(stub)


def test_duplicate_attachment_ids_fail_closed(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("dup-id", name="one.pdf"),
        graph_file_attachment("dup-id", name="two.pdf"),
    ]

    with pytest.raises(ConnectorAttachmentMetadataError):
        connector.list_attachments("msg-1")

    _assert_metadata_only(stub)


def test_same_filename_keeps_distinct_ids(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-1", name="same.pdf"),
        graph_file_attachment("att-2", name="same.pdf"),
    ]

    page = connector.list_attachments("msg-1")

    assert [item.provider_attachment_id for item in page.items] == ["att-1", "att-2"]
    _assert_metadata_only(stub)


def test_missing_file_attachment_id_is_omitted(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("   ", name="blank-id.pdf"),
        graph_file_attachment("att-keep", name="keep.pdf"),
    ]

    page = connector.list_attachments("msg-1")

    assert [item.provider_attachment_id for item in page.items] == ["att-keep"]
    _assert_metadata_only(stub)


def test_list_attachments_unknown_message_is_not_found(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachment_list_status["missing"] = 404

    with pytest.raises(ConnectorMessageNotFoundError):
        connector.list_attachments("missing")

    _assert_metadata_only(stub)


def test_attachment_pagination_stops_at_fifty_without_following_next_link(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    first_page = [graph_file_attachment(f"att-{index}") for index in range(50)]
    next_link = (
        "https://graph.microsoft.com/v1.0/me/messages/msg-1/attachments"
        "?$select=id,name,contentType,size,isInline,contentId,@odata.type"
        "&$skiptoken=more"
    )

    def handler(request: httpx.Request, message_id: str) -> httpx.Response:
        assert message_id == "msg-1"
        assert request.url.params.get("$skiptoken") is None
        return httpx.Response(200, json={"value": first_page, "@odata.nextLink": next_link})

    stub.attachment_list_handler = handler

    page = connector.list_attachments("msg-1")

    assert len(page.items) == 50
    assert page.truncated is True
    assert len(stub.requests) == 1
    _assert_metadata_only(stub)


def test_attachment_pagination_rebuilds_select_and_does_not_follow_unsafe_link(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    first = [graph_file_attachment(f"att-{index}") for index in range(2)]
    second = [graph_file_attachment("att-2"), graph_file_attachment("att-3")]
    next_link = (
        "https://graph.microsoft.com/v1.0/me/messages/msg-1/attachments"
        "?$select=id,name,contentType,size,isInline,contentId,contentBytes,@odata.type"
        "&$skiptoken=page-2"
    )
    pages = iter(
        (
            {"value": first, "@odata.nextLink": next_link},
            {"value": second},
        )
    )

    def handler(request: httpx.Request, message_id: str) -> httpx.Response:
        assert message_id == "msg-1"
        payload = next(pages)
        if request.url.params.get("$skiptoken") == "page-2":
            assert _select_fields(request) == ATTACHMENT_SELECT_FIELDS
            assert "contentBytes" not in _select_fields(request)
        return httpx.Response(200, json=payload)

    stub.attachment_list_handler = handler

    page = connector.list_attachments("msg-1")

    assert [item.provider_attachment_id for item in page.items] == [
        "att-0",
        "att-1",
        "att-2",
        "att-3",
    ]
    assert page.truncated is False
    assert len(stub.requests) == 2
    _assert_metadata_only(stub)


def test_fetch_attachment_content_requests_one_file_attachment(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    encoded = _b64_bytes(pdf)
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-pdf-1", extra={"contentBytes": encoded}, size=len(pdf)),
        graph_file_attachment("att-sibling", name="other.pdf"),
    ]

    content = connector.fetch_attachment_content("msg-1", "att-pdf-1")

    assert content.content == pdf
    assert content.source_attachment_id == "att-pdf-1"
    assert content.source_message_id == "msg-1"
    content_requests = stub.attachment_content_requests
    assert len(content_requests) == 1
    assert content_requests[0].url.path == f"{GRAPH_API_PREFIX}/msg-1/attachments/att-pdf-1"
    assert "contentBytes" in _select_fields(content_requests[0])
    metadata_requests = [
        request
        for request in stub.requests
        if request.url.path.endswith("/att-pdf-1")
        and "contentBytes" not in _select_fields(request)
    ]
    assert len(metadata_requests) == 1
    assert "contentBytes" not in _select_fields(metadata_requests[0])
    assert all(not request.url.path.endswith("/att-sibling") for request in stub.requests)
    assert all("$value" not in str(request.url) for request in stub.requests)


def test_fetch_attachment_content_item_attachment_fails_before_content_bytes(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.attachment_items[("msg-1", "att-item")] = {
        "@odata.type": "#microsoft.graph.itemAttachment",
        "id": "att-item",
        "name": "embedded.msg",
        "contentType": "message/rfc822",
        "size": 100,
        "isInline": False,
    }

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.fetch_attachment_content("msg-1", "att-item")

    assert stub.attachment_content_requests == []


def test_fetch_attachment_content_reference_attachment_fails_closed(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.attachment_items[("msg-1", "att-ref")] = {
        "@odata.type": "#microsoft.graph.referenceAttachment",
        "id": "att-ref",
        "name": "shared.docx",
        "contentType": "application/octet-stream",
        "size": 12,
        "isInline": False,
    }

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.fetch_attachment_content("msg-1", "att-ref")

    assert stub.attachment_content_requests == []


def test_fetch_attachment_content_unknown_subtype_fails_closed(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.attachment_items[("msg-1", "att-1")] = graph_file_attachment(
        "att-1",
        odata_type="#microsoft.graph.unexpectedAttachment",
    )

    with pytest.raises(ConnectorUnsupportedAttachmentError):
        connector.fetch_attachment_content("msg-1", "att-1")

    assert stub.attachment_content_requests == []


def test_fetch_attachment_content_id_mismatch_fails(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachment_items[("msg-1", "att-1")] = graph_file_attachment("att-other")

    with pytest.raises(ConnectorAttachmentContentError):
        connector.fetch_attachment_content("msg-1", "att-1")

    assert stub.attachment_content_requests == []


def test_fetch_attachment_content_rejects_malformed_base64(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.attachments["msg-1"] = [
        graph_file_attachment("att-1", extra={"contentBytes": "not-base64***"}, size=4)
    ]

    with pytest.raises(ConnectorAttachmentContentError) as exc_info:
        connector.fetch_attachment_content("msg-1", "att-1")

    assert "not-base64" not in exc_info.value.message


def test_fetch_attachment_content_rejects_oversized_metadata_without_content_bytes(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.attachment_items[("msg-1", "att-huge")] = graph_file_attachment(
        "att-huge",
        size=5 * 1024 * 1024 + 1,
        extra={"contentBytes": "UEsFBgAAAAA="},
    )

    with pytest.raises(ConnectorAttachmentContentError):
        connector.fetch_attachment_content("msg-1", "att-huge")

    assert stub.attachment_content_requests == []


def test_list_attachments_still_omits_content_bytes_after_explicit_fetch(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    pdf = b"%PDF-1.4\n%%EOF\n"
    stub.attachments["msg-1"] = [graph_file_attachment("att-1", size=len(pdf))]
    stub.attachment_items[("msg-1", "att-1")] = graph_file_attachment(
        "att-1",
        extra={"contentBytes": _b64_bytes(pdf)},
        size=len(pdf),
    )
    connector.fetch_attachment_content("msg-1", "att-1")
    stub.requests.clear()
    stub.attachment_content_requests.clear()

    page = connector.list_attachments("msg-1")

    assert page.items[0].provider_attachment_id == "att-1"
    _assert_metadata_only(stub)


def test_blank_attachment_id_does_not_call_value_endpoint(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector

    with pytest.raises(ConnectorAttachmentNotFoundError):
        connector.fetch_attachment_content("msg-1", "   ")

    assert stub.requests == []
    _assert_metadata_only(stub)
