"""Shared Gmail REST fixtures for mocked httpx tests."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote

import httpx
import pytest

from app.infrastructure.connectors.gmail import GmailCommunicationConnector

GMAIL_TOKEN = "unit-test-gmail-token"
GMAIL_API_PREFIX = "/gmail/v1/users/me/messages"
GMAIL_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def b64url(text: str, *, encoding: str = "utf-8") -> str:
    """Return Gmail-style base64url without padding."""
    return base64.urlsafe_b64encode(text.encode(encoding)).decode("ascii").rstrip("=")


def header(name: str, value: str) -> dict[str, str]:
    return {"name": name, "value": value}


def text_part(
    body: str,
    *,
    mime_type: str = "text/plain",
    charset: str | None = "utf-8",
    encoding: str | None = None,
    filename: str = "",
    attachment_id: str | None = None,
    include_data: bool = True,
    headers: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    payload_headers = list(headers or [])
    if charset is not None:
        payload_headers.append(header("Content-Type", f"{mime_type}; charset={charset}"))
    body_obj: dict[str, Any] = {}
    if include_data:
        body_obj["data"] = b64url(body, encoding=encoding or charset or "utf-8")
    if attachment_id is not None:
        body_obj["attachmentId"] = attachment_id
    return {
        "mimeType": mime_type,
        "filename": filename,
        "headers": payload_headers,
        "body": body_obj,
    }


def gmail_resource(
    message_id: str,
    *,
    thread_id: str = "thread-1",
    sender: str = "alice@example.com",
    to: str = "bob@example.com",
    cc: str | None = None,
    bcc: str | None = None,
    subject: str | None = "Status update",
    date: str | None = "Wed, 20 Aug 2026 09:00:00 +0000",
    internal_date: str | None = "1776704400000",
    body: str = "Please review the Q3 budget proposal before Friday.",
    payload: dict[str, Any] | None = None,
    label_ids: list[str] | None = None,
    extra_headers: list[dict[str, str]] | None = None,
    snippet: str | None = None,
) -> dict[str, Any]:
    if payload is None:
        headers = [
            header("From", sender),
            header("To", to),
        ]
        if cc is not None:
            headers.append(header("Cc", cc))
        if bcc is not None:
            headers.append(header("Bcc", bcc))
        if subject is not None:
            headers.append(header("Subject", subject))
        if date is not None:
            headers.append(header("Date", date))
        if extra_headers:
            headers.extend(extra_headers)
        payload = {
            "mimeType": "text/plain",
            "filename": "",
            "headers": headers,
            "body": {"data": b64url(body)},
        }
    resource: dict[str, Any] = {
        "id": message_id,
        "threadId": thread_id,
        "labelIds": label_ids if label_ids is not None else ["INBOX", "UNREAD"],
        "payload": payload,
    }
    if internal_date is not None:
        resource["internalDate"] = internal_date
    if snippet is not None:
        resource["snippet"] = snippet
    return resource


class GmailHttpStub:
    """Scripted Gmail REST surface backed by httpx.MockTransport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.messages: dict[str, dict[str, Any]] = {}
        self.list_ids: list[str] | None = None
        self.next_page_token: str | None = None
        self.list_status: int = 200
        self.list_json: Any = None
        self.list_text: str | None = None
        self.fetch_status: dict[str, int] = {}
        self.fetch_json: dict[str, Any] = {}
        self.fetch_text: dict[str, str] = {}
        self.error_json: dict[str, Any] | None = None
        self.transport_error: BaseException | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.transport_error is not None:
            raise self.transport_error
        path = request.url.path
        if path.rstrip("/") == GMAIL_API_PREFIX:
            return self._list_response()
        prefix = GMAIL_API_PREFIX + "/"
        if path.startswith(prefix):
            return self._fetch_response(path[len(prefix) :])
        return httpx.Response(404, json={"error": {"message": "unknown route"}})

    def _list_response(self) -> httpx.Response:
        if self.list_text is not None:
            return httpx.Response(self.list_status, text=self.list_text)
        if self.list_json is not None:
            return httpx.Response(self.list_status, json=self.list_json)
        if self.list_status != 200:
            return httpx.Response(self.list_status, json=self.error_json or {"error": {}})
        ids = self.list_ids if self.list_ids is not None else list(self.messages)
        body: dict[str, Any] = {
            "messages": [{"id": message_id, "threadId": "thread-1"} for message_id in ids]
        }
        if self.next_page_token is not None:
            body["nextPageToken"] = self.next_page_token
        return httpx.Response(200, json=body)

    def _fetch_response(self, raw_id: str) -> httpx.Response:
        message_id = unquote(raw_id)
        status = self.fetch_status.get(message_id, 200)
        if message_id in self.fetch_text:
            return httpx.Response(status, text=self.fetch_text[message_id])
        if message_id in self.fetch_json:
            return httpx.Response(status, json=self.fetch_json[message_id])
        if status != 200:
            return httpx.Response(status, json=self.error_json or {"error": {}})
        resource = self.messages.get(message_id)
        if resource is None:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json=resource)


@pytest.fixture
def gmail_stub() -> GmailHttpStub:
    return GmailHttpStub()


@pytest.fixture
def gmail_connector(
    gmail_stub: GmailHttpStub,
) -> Iterator[tuple[GmailCommunicationConnector, GmailHttpStub, httpx.Client]]:
    client = httpx.Client(transport=httpx.MockTransport(gmail_stub))
    connector = GmailCommunicationConnector(
        http_client=client,
        access_token_provider=lambda: GMAIL_TOKEN,
    )
    try:
        yield connector, gmail_stub, client
    finally:
        client.close()
