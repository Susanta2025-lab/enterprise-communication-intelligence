"""Shared Microsoft Graph REST fixtures for mocked httpx tests."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote

import httpx
import pytest

from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector

GRAPH_TOKEN = "unit-test-graph-token"
GRAPH_API_PREFIX = "/v1.0/me/messages"
GRAPH_LIST_URL = "https://graph.microsoft.com/v1.0/me/messages"
FETCH_SELECT_FIELDS = frozenset(
    {
        "id",
        "conversationId",
        "subject",
        "body",
        "from",
        "sender",
        "toRecipients",
        "ccRecipients",
        "bccRecipients",
        "sentDateTime",
        "receivedDateTime",
        "categories",
    }
)
ATTACHMENT_SELECT_FIELDS = frozenset(
    {
        "id",
        "name",
        "contentType",
        "size",
        "isInline",
    }
)


def email_address(address: str, name: str | None = None) -> dict[str, Any]:
    payload: dict[str, str] = {"address": address}
    if name is not None:
        payload["name"] = name
    return {"emailAddress": payload}


def graph_file_attachment(
    attachment_id: str,
    *,
    name: str = "report.pdf",
    content_type: str = "application/pdf",
    size: int = 2048,
    is_inline: bool = False,
    content_id: str | None = None,
    odata_type: str = "#microsoft.graph.fileAttachment",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "@odata.type": odata_type,
        "id": attachment_id,
        "name": name,
        "contentType": content_type,
        "size": size,
        "isInline": is_inline,
    }
    if content_id is not None:
        resource["contentId"] = content_id
    if extra:
        resource.update(extra)
    return resource


def graph_resource(
    message_id: str,
    *,
    conversation_id: str | None = "conv-1",
    subject: str | None = "Status update",
    body: str = "Please review the Q3 budget proposal before Friday.",
    content_type: str = "text",
    from_address: str | None = "alice@example.com",
    from_name: str | None = "Alice Example",
    sender_address: str | None = None,
    sender_name: str | None = None,
    to: list[tuple[str, str | None]] | None = None,
    cc: list[tuple[str, str | None]] | None = None,
    bcc: list[tuple[str, str | None]] | None = None,
    sent_at: str | None = "2026-08-20T09:00:00Z",
    received_at: str | None = "2026-08-20T09:01:00Z",
    categories: object = None,
    body_preview: str | None = None,
    internet_message_id: str | None = None,
    extra: dict[str, Any] | None = None,
    include_body: bool = True,
) -> dict[str, Any]:
    resource: dict[str, Any] = {"id": message_id}
    if conversation_id is not None:
        resource["conversationId"] = conversation_id
    if subject is not None:
        resource["subject"] = subject
    if include_body:
        resource["body"] = {"contentType": content_type, "content": body}
    if from_address is not None:
        resource["from"] = email_address(from_address, from_name)
    if sender_address is not None:
        resource["sender"] = email_address(sender_address, sender_name)
    if to is None:
        to = [("bob@example.com", "Bob Example")]
    resource["toRecipients"] = [email_address(address, name) for address, name in to]
    if cc is not None:
        resource["ccRecipients"] = [email_address(address, name) for address, name in cc]
    if bcc is not None:
        resource["bccRecipients"] = [email_address(address, name) for address, name in bcc]
    if sent_at is not None:
        resource["sentDateTime"] = sent_at
    if received_at is not None:
        resource["receivedDateTime"] = received_at
    if categories is not None:
        resource["categories"] = categories
    if body_preview is not None:
        resource["bodyPreview"] = body_preview
    if internet_message_id is not None:
        resource["internetMessageId"] = internet_message_id
    if extra:
        resource.update(extra)
    return resource


class GraphHttpStub:
    """Scripted Microsoft Graph REST surface backed by httpx.MockTransport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.messages: dict[str, dict[str, Any]] = {}
        self.list_ids: list[str] | None = None
        self.next_link: str | None = None
        self.list_status: int = 200
        self.list_json: Any = None
        self.list_text: str | None = None
        self.fetch_status: dict[str, int] = {}
        self.fetch_json: dict[str, Any] = {}
        self.fetch_text: dict[str, str] = {}
        self.error_json: dict[str, Any] | None = None
        self.transport_error: BaseException | None = None
        self.redirect_location = "https://evil.example/steal"
        self.attachments: dict[str, list[dict[str, Any]]] = {}
        self.attachment_list_json: dict[str, Any] = {}
        self.attachment_list_status: dict[str, int] = {}
        self.attachment_list_handler: Any = None
        self.attachment_content_requests: list[httpx.Request] = []
        self.attachment_items: dict[tuple[str, str], dict[str, Any]] = {}
        self.attachment_item_status: dict[tuple[str, str], int] = {}
        self.attachment_item_json: dict[tuple[str, str], Any] = {}
        self.attachment_item_text: dict[tuple[str, str], str] = {}
        self.attachment_value_bodies: dict[tuple[str, str], bytes] = {}
        self.attachment_value_status: dict[tuple[str, str], int] = {}
        self.attachment_value_headers: dict[tuple[str, str], dict[str, str]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.transport_error is not None:
            raise self.transport_error
        path = request.url.path
        if path.rstrip("/") == GRAPH_API_PREFIX:
            return self._list_response()
        prefix = GRAPH_API_PREFIX + "/"
        if path.startswith(prefix):
            remainder = path[len(prefix) :]
            if "/attachments" in remainder or remainder.endswith("/attachments"):
                return self._attachment_response(request, remainder)
            return self._fetch_response(remainder)
        return httpx.Response(404, json={"error": {"code": "Unknown", "message": "unknown route"}})

    def _headers_for_status(self, status: int) -> dict[str, str]:
        if status in {301, 302, 303, 307, 308}:
            return {"Location": self.redirect_location}
        return {}

    def _error_body(self) -> dict[str, Any]:
        return self.error_json or {"error": {"code": "Error", "message": "graph error"}}

    def _list_response(self) -> httpx.Response:
        headers = self._headers_for_status(self.list_status)
        if self.list_text is not None:
            return httpx.Response(self.list_status, text=self.list_text, headers=headers)
        if self.list_json is not None:
            return httpx.Response(self.list_status, json=self.list_json, headers=headers)
        if self.list_status != 200:
            return httpx.Response(self.list_status, json=self._error_body(), headers=headers)
        ids = self.list_ids if self.list_ids is not None else list(self.messages)
        body: dict[str, Any] = {"value": [{"id": message_id} for message_id in ids]}
        if self.next_link is not None:
            body["@odata.nextLink"] = self.next_link
        return httpx.Response(200, json=body)

    def _fetch_response(self, raw_id: str) -> httpx.Response:
        message_id = unquote(raw_id)
        status = self.fetch_status.get(message_id, 200)
        headers = self._headers_for_status(status)
        if message_id in self.fetch_text:
            return httpx.Response(status, text=self.fetch_text[message_id], headers=headers)
        if message_id in self.fetch_json:
            return httpx.Response(status, json=self.fetch_json[message_id], headers=headers)
        if status != 200:
            return httpx.Response(status, json=self._error_body(), headers=headers)
        resource = self.messages.get(message_id)
        if resource is None:
            return httpx.Response(
                404,
                json={"error": {"code": "ErrorItemNotFound", "message": "not found"}},
            )
        return httpx.Response(200, json=resource)

    def _attachment_response(self, request: httpx.Request, remainder: str) -> httpx.Response:
        decoded = unquote(remainder)
        marker = "/attachments"
        split_at = decoded.lower().find(marker)
        message_id = decoded[:split_at] if split_at >= 0 else decoded
        after = decoded[split_at + len(marker) :] if split_at >= 0 else ""
        if after not in {"", "/"}:
            return self._attachment_item_response(request, message_id, after)
        if self.attachment_list_handler is not None:
            return self.attachment_list_handler(request, message_id)
        status = self.attachment_list_status.get(message_id, 200)
        headers = self._headers_for_status(status)
        if message_id in self.attachment_list_json:
            return httpx.Response(
                status,
                json=self.attachment_list_json[message_id],
                headers=headers,
            )
        if status != 200:
            return httpx.Response(status, json=self._error_body(), headers=headers)
        body: dict[str, Any] = {"value": list(self.attachments.get(message_id, []))}
        return httpx.Response(200, json=body)

    def _attachment_item_response(
        self,
        request: httpx.Request,
        message_id: str,
        after: str,
    ) -> httpx.Response:
        item_path = after.strip("/")
        if item_path.endswith("/$value") or item_path == "$value":
            return self._attachment_value_response(request, message_id, item_path)
        attachment_id = unquote(item_path.split("/", 1)[0])
        select_fields = {
            part.strip() for part in request.url.params.get("$select", "").split(",") if part
        }
        key = (message_id, attachment_id)
        status = self.attachment_item_status.get(key, 200)
        headers = self._headers_for_status(status)
        if key in self.attachment_item_text:
            return httpx.Response(status, text=self.attachment_item_text[key], headers=headers)
        if key in self.attachment_item_json:
            return httpx.Response(status, json=self.attachment_item_json[key], headers=headers)
        if status != 200:
            return httpx.Response(status, json=self._error_body(), headers=headers)
        resource = self.attachment_items.get(key)
        if resource is None:
            resource = next(
                (
                    item
                    for item in self.attachments.get(message_id, [])
                    if item.get("id") == attachment_id
                ),
                None,
            )
        if resource is None:
            return httpx.Response(
                404,
                json={"error": {"code": "ErrorItemNotFound", "message": "not found"}},
                headers=headers,
            )
        payload = dict(resource)
        # Metadata GETs never include contentBytes even if the fixture stored them.
        if "contentBytes" not in select_fields:
            payload.pop("contentBytes", None)
        return httpx.Response(200, json=payload, headers=headers)

    def _attachment_value_response(
        self,
        request: httpx.Request,
        message_id: str,
        item_path: str,
    ) -> httpx.Response:
        self.attachment_content_requests.append(request)
        attachment_id = unquote(item_path.removesuffix("/$value").removesuffix("$value").strip("/"))
        key = (message_id, attachment_id)
        status = self.attachment_value_status.get(key, 200)
        headers = dict(self._headers_for_status(status))
        headers.update(self.attachment_value_headers.get(key, {}))
        if status != 200:
            return httpx.Response(status, json=self._error_body(), headers=headers)
        if key in self.attachment_value_bodies:
            body = self.attachment_value_bodies[key]
            return httpx.Response(200, content=body, headers=headers)
        resource = self.attachment_items.get(key)
        if resource is None:
            resource = next(
                (
                    item
                    for item in self.attachments.get(message_id, [])
                    if item.get("id") == attachment_id
                ),
                None,
            )
        if resource is None:
            return httpx.Response(
                404,
                json={"error": {"code": "ErrorItemNotFound", "message": "not found"}},
                headers=headers,
            )
        encoded = resource.get("contentBytes")
        if not isinstance(encoded, str) or not encoded.strip():
            return httpx.Response(200, content=b"", headers=headers)
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=False)
        except (ValueError, UnicodeEncodeError):
            return httpx.Response(
                400,
                json={"error": {"code": "Error", "message": "invalid contentBytes fixture"}},
                headers=headers,
            )
        return httpx.Response(200, content=raw, headers=headers)


@pytest.fixture
def graph_stub() -> GraphHttpStub:
    return GraphHttpStub()


@pytest.fixture
def graph_connector(
    graph_stub: GraphHttpStub,
) -> Iterator[tuple[MicrosoftGraphCommunicationConnector, GraphHttpStub, httpx.Client]]:
    client = httpx.Client(transport=httpx.MockTransport(graph_stub))
    connector = MicrosoftGraphCommunicationConnector(
        http_client=client,
        access_token_provider=lambda: GRAPH_TOKEN,
    )
    try:
        yield connector, graph_stub, client
    finally:
        client.close()
