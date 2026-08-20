"""Unit tests for Gmail header and timestamp normalization."""

from datetime import UTC, datetime

from tests.unit.infrastructure.connectors.gmail.conftest import b64url, gmail_resource, header


def test_header_names_are_case_insensitive(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
            header("FROM", "Casey <casey@example.com>"),
            header("tO", "dana@example.com"),
            header("cC", "erin@example.com"),
            header("SUBJECT", "Case test"),
            header("DATE", "Wed, 20 Aug 2026 10:15:00 +0000"),
        ],
        "body": {"data": b64url("Hello")},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.metadata.sender == "casey@example.com"
    assert message.metadata.recipients == ["dana@example.com", "erin@example.com"]
    assert message.metadata.subject == "Case test"


def test_rfc2047_encoded_subject(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        subject="=?utf-8?q?Q3_budget_r=C3=A9sum=C3=A9?=",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.subject == "Q3 budget résumé"


def test_from_mapping_uses_address_not_display_name(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        sender="Finance Bot <finance.bot@example.com>",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sender == "finance.bot@example.com"


def test_multiple_to_cc_and_bcc_recipients(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        to="a@example.com, B <b@example.com>",
        cc="c@example.com",
        bcc="d@example.com",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.recipients == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
        "d@example.com",
    ]


def test_missing_optional_subject_is_none(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource("msg-1", subject=None)

    message = connector.fetch_message("msg-1")

    assert message.metadata.subject is None
    assert message.metadata.subject != "(no subject)"


def test_missing_recipients_are_allowed(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    payload = {
        "mimeType": "text/plain",
        "filename": "",
        "headers": [
            header("From", "alice@example.com"),
            header("Subject", "No recipients"),
        ],
        "body": {"data": b64url("Hello")},
    }
    stub.messages["msg-1"] = gmail_resource("msg-1", payload=payload)

    message = connector.fetch_message("msg-1")

    assert message.metadata.recipients == []


def test_malformed_date_falls_back_to_internal_date(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        date="not-a-date",
        internal_date="1776704400000",
    )

    message = connector.fetch_message("msg-1")
    expected = datetime.fromtimestamp(1776704400000 / 1000, tz=UTC)

    assert message.metadata.sent_at == expected
    assert message.metadata.received_at == expected
    assert message.metadata.sent_at.tzinfo is not None
    assert message.metadata.received_at.tzinfo is not None


def test_internal_date_used_when_date_header_absent(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        date=None,
        internal_date="1776704400000",
    )

    message = connector.fetch_message("msg-1")
    expected = datetime.fromtimestamp(1776704400000 / 1000, tz=UTC)

    assert message.metadata.sent_at == expected
    assert message.metadata.received_at == expected


def test_normalized_datetimes_are_timezone_aware(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        date="Wed, 20 Aug 2026 12:00:00 -0500",
        internal_date="1776715200000",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at is not None
    assert message.metadata.received_at is not None
    assert message.metadata.sent_at.tzinfo is not None
    assert message.metadata.received_at.tzinfo is not None
    assert message.metadata.sent_at == datetime(2026, 8, 20, 17, 0, tzinfo=UTC)


def test_naive_rfc_date_is_interpreted_as_utc(gmail_connector: tuple) -> None:
    connector, stub, _client = gmail_connector
    stub.messages["msg-1"] = gmail_resource(
        "msg-1",
        date="Wed, 20 Aug 2026 12:00:00",
        internal_date="1776715200000",
    )

    message = connector.fetch_message("msg-1")

    assert message.metadata.sent_at == datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    assert message.metadata.sent_at.tzinfo is UTC
