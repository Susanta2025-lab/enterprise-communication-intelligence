"""Unit tests for the Phase 14 mailbox public contract schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.analysis import CommunicationAnalysisResponse
from app.schemas.mailbox import (
    MAILBOX_MESSAGE_LIST_DEFAULT_PAGE_SIZE,
    MAILBOX_MESSAGE_LIST_MAX_PAGE_SIZE,
    ConnectorAccountMessageAnalyzeRequest,
    ConnectorAccountMessageListItem,
    ConnectorAccountMessageListQuery,
    ConnectorAccountMessageListResponse,
)


def test_list_query_uses_default_bounded_page_size() -> None:
    """Omitted page_size uses the documented default within the allowed range."""
    query = ConnectorAccountMessageListQuery()
    assert query.page_size == MAILBOX_MESSAGE_LIST_DEFAULT_PAGE_SIZE
    assert 1 <= query.page_size <= MAILBOX_MESSAGE_LIST_MAX_PAGE_SIZE
    assert query.cursor is None


def test_list_query_rejects_page_size_above_maximum() -> None:
    """Page size above the explicit maximum is rejected."""
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListQuery(page_size=MAILBOX_MESSAGE_LIST_MAX_PAGE_SIZE + 1)
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListQuery(page_size=0)


def test_list_query_treats_cursor_as_opaque() -> None:
    """Cursors are stored as opaque strings and are not parsed as URLs."""
    cursor = "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=secret"
    query = ConnectorAccountMessageListQuery(cursor=cursor)
    assert query.cursor == cursor
    payload = query.model_dump()
    assert payload["cursor"] == cursor
    assert "nextLink" not in payload


def test_list_query_rejects_blank_cursor_and_unknown_fields() -> None:
    """Blank cursors and provider-specific query fields are rejected."""
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListQuery(cursor="   ")
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListQuery.model_validate({"page_size": 10, "nextLink": "x"})
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListQuery.model_validate({"limit": 10})


def test_list_item_is_provider_neutral_selection_metadata() -> None:
    """List items expose only the metadata needed to select a message."""
    sent_at = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    item = ConnectorAccountMessageListItem(
        provider_message_id="opaque-provider-id",
        sender="alice@example.com",
        subject="Quarterly review",
        sent_at=sent_at,
        received_at=None,
    )
    payload = item.model_dump(mode="json")
    assert payload["provider_message_id"] == "opaque-provider-id"
    assert payload["sender"] == "alice@example.com"
    assert payload["subject"] == "Quarterly review"
    assert payload["sent_at"] is not None
    assert payload["received_at"] is None
    assert set(payload) == {
        "provider_message_id",
        "sender",
        "subject",
        "sent_at",
        "received_at",
    }
    serialized = repr(payload)
    assert "credential_ref" not in serialized
    assert "thread_id" not in serialized
    assert "body" not in serialized
    assert "nextLink" not in serialized
    assert "access_token" not in serialized


def test_list_item_rejects_blank_ids_and_secret_fields() -> None:
    """Blank identifiers and credential fields are not part of the contract."""
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListItem(provider_message_id="   ", sender="alice@example.com")
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListItem.model_validate(
            {
                "provider_message_id": "msg-1",
                "sender": "alice@example.com",
                "credential_ref": "oauth-secret",
            }
        )
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListItem.model_validate(
            {
                "provider_message_id": "msg-1",
                "sender": "alice@example.com",
                "body": "secret body",
            }
        )


def test_list_response_keeps_next_cursor_opaque() -> None:
    """next_cursor is opaque transport data, not a provider pagination URL field."""
    item = ConnectorAccountMessageListItem(
        provider_message_id="msg-1",
        sender="alice@example.com",
    )
    cursor = "eci-opaque-cursor://not-a-graph-nextLink"
    response = ConnectorAccountMessageListResponse(items=[item], next_cursor=cursor)
    payload = response.model_dump(mode="json")
    assert payload["next_cursor"] == cursor
    assert "nextLink" not in payload
    assert "credential_ref" not in repr(payload)
    terminal = ConnectorAccountMessageListResponse(items=[], next_cursor=None)
    assert terminal.next_cursor is None
    with pytest.raises(ValidationError):
        ConnectorAccountMessageListResponse(items=[], next_cursor="   ")


def test_analyze_request_accepts_opaque_provider_message_id() -> None:
    """Valid opaque identifiers are accepted in the JSON body."""
    request = ConnectorAccountMessageAnalyzeRequest(
        provider_message_id="AAMkAGI2THVLLTIw==",
    )
    assert request.provider_message_id == "AAMkAGI2THVLLTIw=="


def test_analyze_request_rejects_empty_or_invalid_provider_message_id() -> None:
    """Empty, blank, and extra fields are rejected."""
    with pytest.raises(ValidationError):
        ConnectorAccountMessageAnalyzeRequest(provider_message_id="")
    with pytest.raises(ValidationError):
        ConnectorAccountMessageAnalyzeRequest(provider_message_id="   ")
    with pytest.raises(ValidationError):
        ConnectorAccountMessageAnalyzeRequest.model_validate({})
    with pytest.raises(ValidationError):
        ConnectorAccountMessageAnalyzeRequest.model_validate(
            {"provider_message_id": "msg-1", "credential_ref": "oauth-secret"}
        )


def test_mailbox_analyze_reuses_existing_analysis_response() -> None:
    """Mailbox analyze does not introduce a duplicate AI-analysis DTO."""
    from app.domain.enums import MessageCategory, PriorityLevel
    from app.domain.models import CommunicationAnalysis, Priority, Summary

    response = CommunicationAnalysisResponse(
        analysis=CommunicationAnalysis(
            summary=Summary(text="Short summary."),
            priority=Priority(level=PriorityLevel.MEDIUM),
            category=MessageCategory.GENERAL,
        ),
        provider="mock",
    )
    payload = response.model_dump(mode="json")
    assert "analysis" in payload
    assert payload["provider"] == "mock"
    assert "analysis_id" not in payload
    assert "credential_ref" not in payload
    assert "body" not in payload
    assert "access_token" not in repr(payload)
