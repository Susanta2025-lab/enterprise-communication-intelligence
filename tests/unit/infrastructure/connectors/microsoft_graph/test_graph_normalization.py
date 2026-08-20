"""Unit tests for Microsoft Graph JSON normalization into CommunicationMessage."""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import ConnectorMessageContentError
from app.domain.enums import SourceType
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import graph_resource


def test_text_body_and_core_fields_map_to_domain(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        conversation_id="conv-1",
        subject="Q3 budget review",
        body="Please review the Q3 budget proposal before Friday.",
        content_type="text",
        from_address="alice@example.com",
        from_name="Alice Example",
        to=[("bob@example.com", "Bob")],
        cc=[("carol@example.com", "Carol")],
        bcc=[("dave@example.com", "Dave")],
        sent_at="2026-08-20T09:00:00Z",
        received_at="2026-08-20T09:01:00Z",
        categories=["Important", "Project"],
        internet_message_id="<not-used@example.com>",
        body_preview="partial preview must not be used",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.source_type is SourceType.EMAIL
    assert message.message_id == "msg-1"
    assert message.metadata.source_id == "msg-1"
    assert message.metadata.thread_id == "conv-1"
    assert message.metadata.sender == "alice@example.com"
    assert message.metadata.recipients == [
        "bob@example.com",
        "carol@example.com",
        "dave@example.com",
    ]
    assert message.metadata.subject == "Q3 budget review"
    assert message.body == "Please review the Q3 budget proposal before Friday."
    assert message.metadata.sent_at == datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert message.metadata.received_at == datetime(2026, 8, 20, 9, 1, tzinfo=UTC)
    assert message.metadata.labels == ["Important", "Project"]
    assert "partial preview" not in message.body
    assert "<not-used@example.com>" not in (message.message_id or "")


def test_html_body_converts_to_plain_text(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    html = (
        "<script>secretExecutable()</script>"
        "<style>body { color: red; }</style>"
        "<p>Hello <b>world</b></p>"
    )
    stub.messages["msg-1"] = graph_resource("msg-1", body=html, content_type="html")

    message = connector.fetch_message("msg-1")

    assert message.body == "Hello world"
    assert "secretExecutable()" not in message.body
    assert "color: red" not in message.body
    assert "<p>" not in message.body
    assert "<b>" not in message.body
    assert "<script>" not in message.body


def test_html_entities_are_decoded(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        body="<p>Tom &amp; Jerry</p>",
        content_type="html",
    )

    message = connector.fetch_message("msg-1")

    assert message.body == "Tom & Jerry"


def test_html_only_script_style_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        body="<script>secretExecutable()</script><style>body{}</style>",
        content_type="html",
    )

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_missing_body_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", include_body=False, body_preview="preview")

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    assert "preview" not in exc_info.value.message


def test_null_body_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1", body_preview="Do not use preview")
    resource["body"] = None
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_string_body_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1")
    resource["body"] = "not-an-object"
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_missing_content_type_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1")
    del resource["body"]["contentType"]
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_unknown_content_type_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", content_type="rtf")

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


@pytest.mark.parametrize(
    ("content_type", "body", "expected"),
    [
        (
            "Text",
            "Please review the Q3 budget proposal before Friday.",
            "Please review the Q3 budget proposal before Friday.",
        ),
        (
            "TEXT",
            "Please review the Q3 budget proposal before Friday.",
            "Please review the Q3 budget proposal before Friday.",
        ),
        ("HTML", "<p>Hello <b>world</b></p>", "Hello world"),
    ],
)
def test_content_type_comparison_is_case_insensitive(
    graph_connector: tuple,
    content_type: str,
    body: str,
    expected: str,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        body=body,
        content_type=content_type,
    )

    message = connector.fetch_message("msg-1")

    assert message.body == expected
    assert "<p>" not in message.body


def test_missing_content_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1", body_preview="partial")
    del resource["body"]["content"]
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    assert "partial" not in exc_info.value.message


def test_non_string_content_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1")
    resource["body"]["content"] = ["not", "text"]
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_blank_text_body_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        body="   ",
        content_type="text",
        body_preview="Do not analyze this preview",
    )

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    assert "Do not analyze this preview" not in exc_info.value.message


def test_body_preview_is_not_used_when_body_is_invalid(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource(
        "msg-1",
        body="   ",
        body_preview="This preview must never become the analyzed body",
    )
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError) as exc_info:
        connector.fetch_message("msg-1")

    assert "This preview must never become the analyzed body" not in exc_info.value.message


def test_from_address_preferred_over_display_name(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        from_address="Finance.Bot@example.com",
        from_name="Finance Bot",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sender == "Finance.Bot@example.com"


def test_sender_fallback_when_from_missing(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource(
        "msg-1",
        from_address=None,
        sender_address="delegate@example.com",
        sender_name="Delegate",
    )
    stub.messages["msg-1"] = resource

    message = connector.fetch_message("msg-1")

    assert message.metadata.sender == "delegate@example.com"


def test_sender_fallback_when_from_unusable(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1", sender_address="delegate@example.com")
    resource["from"] = {"emailAddress": {"name": "No Address"}}
    stub.messages["msg-1"] = resource

    message = connector.fetch_message("msg-1")

    assert message.metadata.sender == "delegate@example.com"


def test_missing_from_and_sender_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1", from_address=None)
    stub.messages["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_to_cc_bcc_recipients_ignore_display_names(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        to=[("a@example.com", "A"), ("b@example.com", "B")],
        cc=[("c@example.com", "C")],
        bcc=[("d@example.com", "D")],
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.recipients == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
        "d@example.com",
    ]


def test_blank_and_malformed_recipients_are_skipped(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1", to=[])
    resource["toRecipients"] = [
        {"emailAddress": {"address": "keep@example.com", "name": "Keep"}},
        {"emailAddress": {"address": "   ", "name": "Blank"}},
        {"emailAddress": {"name": "No Address"}},
        "not-an-object",
        {"emailAddress": "not-an-object"},
    ]
    resource["ccRecipients"] = None
    stub.messages["msg-1"] = resource

    message = connector.fetch_message("msg-1")

    assert message.metadata.recipients == ["keep@example.com"]


def test_duplicate_recipients_preserve_first_seen_order(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        to=[("a@example.com", None), ("b@example.com", None)],
        cc=[("a@example.com", None), ("c@example.com", None)],
        bcc=[("b@example.com", None)],
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.recipients == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
    ]


def test_empty_recipient_list_is_valid(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1", to=[])
    resource["toRecipients"] = []
    stub.messages["msg-1"] = resource

    message = connector.fetch_message("msg-1")

    assert message.metadata.recipients == []


def test_normal_subject_is_preserved(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", subject="Quarterly review")

    message = connector.fetch_message("msg-1")

    assert message.metadata.subject == "Quarterly review"


def test_empty_or_whitespace_subject_is_none(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    for subject in ("", "   "):
        stub.messages["msg-1"] = graph_resource("msg-1", subject=subject)
        message = connector.fetch_message("msg-1")
        assert message.metadata.subject is None
        assert message.metadata.subject != "(no subject)"


def test_missing_subject_is_none(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", subject=None)

    message = connector.fetch_message("msg-1")

    assert message.metadata.subject is None


def test_non_string_subject_is_none(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1")
    resource["subject"] = ["not", "a", "string"]
    stub.messages["msg-1"] = resource

    message = connector.fetch_message("msg-1")

    assert message.metadata.subject is None


def test_zulu_timestamp_is_utc(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        sent_at="2026-08-20T09:00:00Z",
        received_at="2026-08-20T09:01:00Z",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at == datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert message.metadata.received_at == datetime(2026, 8, 20, 9, 1, tzinfo=UTC)
    assert message.metadata.sent_at.tzinfo is not None
    assert message.metadata.received_at.tzinfo is not None


def test_positive_offset_timestamp_normalizes_to_utc(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        sent_at="2026-08-20T14:00:00+05:00",
        received_at="2026-08-20T14:01:00+05:00",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at == datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert message.metadata.received_at == datetime(2026, 8, 20, 9, 1, tzinfo=UTC)


def test_negative_offset_timestamp_normalizes_to_utc(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        sent_at="2026-08-20T04:00:00-05:00",
        received_at="2026-08-20T04:01:00-05:00",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at == datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
    assert message.metadata.received_at == datetime(2026, 8, 20, 9, 1, tzinfo=UTC)


def test_missing_timestamps_are_none(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", sent_at=None, received_at=None)

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at is None
    assert message.metadata.received_at is None


def test_malformed_timestamps_are_none(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        sent_at="not-a-timestamp",
        received_at="2026/08/20 09:00",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at is None
    assert message.metadata.received_at is None


def test_naive_timestamp_is_interpreted_as_utc(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        sent_at="2026-08-20T12:00:00",
        received_at="2026-08-20T12:00:00",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at == datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    assert message.metadata.sent_at.tzinfo is UTC


def test_graph_id_is_provider_identity_not_internet_message_id(
    graph_connector: tuple,
) -> None:
    connector, stub, _client = graph_connector
    stub.messages["graph-id-1"] = graph_resource(
        "graph-id-1",
        conversation_id="conv-9",
        internet_message_id="<rfc822@example.com>",
    )

    message = connector.fetch_message("graph-id-1")

    assert message.message_id == "graph-id-1"
    assert message.metadata.source_id == "graph-id-1"
    assert message.metadata.thread_id == "conv-9"
    assert message.message_id != "<rfc822@example.com>"


def test_missing_conversation_id_is_none(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", conversation_id=None)

    message = connector.fetch_message("msg-1")

    assert message.metadata.thread_id is None


def test_malformed_id_is_content_error(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    resource = graph_resource("msg-1")
    resource["id"] = 12345
    stub.messages["msg-1"] = resource
    stub.fetch_json["msg-1"] = resource

    with pytest.raises(ConnectorMessageContentError):
        connector.fetch_message("msg-1")


def test_categories_map_to_labels(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        categories=["Important", "Project"],
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.labels == ["Important", "Project"]


def test_empty_categories_map_to_empty_labels(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1", categories=[])

    message = connector.fetch_message("msg-1")

    assert message.metadata.labels == []


def test_missing_categories_map_to_empty_labels(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource("msg-1")

    message = connector.fetch_message("msg-1")

    assert message.metadata.labels == []


def test_null_or_wrong_type_categories_map_to_empty_labels(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    for categories in (None, "Important", {"name": "Important"}):
        resource = graph_resource("msg-1")
        resource["categories"] = categories
        stub.messages["msg-1"] = resource
        message = connector.fetch_message("msg-1")
        assert message.metadata.labels == []


def test_blank_and_non_string_categories_are_skipped(graph_connector: tuple) -> None:
    connector, stub, _client = graph_connector
    stub.messages["msg-1"] = graph_resource(
        "msg-1",
        categories=["", "  ", 1, None, "Keep"],
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.labels == ["Keep"]
