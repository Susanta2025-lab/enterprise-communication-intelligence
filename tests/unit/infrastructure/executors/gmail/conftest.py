"""Shared Gmail reply-executor fixtures for mocked httpx tests."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import parseaddr
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import httpx
import pytest

from app.domain.enums import WorkflowActionType
from app.domain.interfaces import CommunicationActionExecution
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor

GMAIL_TOKEN = "unit-test-gmail-write-token"
GMAIL_API_PREFIX = "/gmail/v1/users/me/messages/"
GMAIL_PROFILE_PATH = "/gmail/v1/users/me/profile"
GMAIL_SEND_PATH = "/gmail/v1/users/me/messages/send"
APPROVED_REPLY = "Thanks, I will review the report and respond by Friday."
PROVIDER_MESSAGE_ID = "gmail-msg-abc123"
THREAD_ID = "thread-gmail-1"
RFC_MESSAGE_ID = "<orig-msg-001@mail.example.test>"
SUBJECT = "Q3 budget review"
FROM_ADDRESS = "sender@example.test"
MAILBOX_ADDRESS = "owner@example.test"


class CountingTokenProvider:
    """On-demand token callable that records how many times it was invoked."""

    def __init__(self, token: object = GMAIL_TOKEN) -> None:
        self.calls = 0
        self.token = token

    def __call__(self) -> str:
        self.calls += 1
        return self.token  # type: ignore[return-value]


class GmailReplyHttpStub:
    """Scripted Gmail metadata GET plus messages.send POST surface."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.profile_status = 200
        self.profile_json: Any = {"emailAddress": MAILBOX_ADDRESS}
        self.profile_text: str | None = None
        self.profile_transport_error: BaseException | None = None
        self.metadata_status = 200
        self.metadata_json: Any = metadata_resource()
        self.metadata_text: str | None = None
        self.send_status = 200
        self.send_json: Any = {"id": "sent-msg-1", "threadId": THREAD_ID}
        self.send_text: str | None = None
        self.metadata_transport_error: BaseException | None = None
        self.send_transport_error: BaseException | None = None
        self.redirect_location = "https://evil.example/steal"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if request.method == "GET" and path == GMAIL_PROFILE_PATH:
            if self.profile_transport_error is not None:
                raise self.profile_transport_error
            return self._response(
                self.profile_status,
                body_json=self.profile_json,
                body_text=self.profile_text,
            )
        if request.method == "GET" and _is_metadata_path(path):
            if self.metadata_transport_error is not None:
                raise self.metadata_transport_error
            return self._response(
                self.metadata_status,
                body_json=self.metadata_json,
                body_text=self.metadata_text,
            )
        if request.method == "POST" and path == GMAIL_SEND_PATH:
            if self.send_transport_error is not None:
                raise self.send_transport_error
            return self._response(
                self.send_status,
                body_json=self.send_json,
                body_text=self.send_text,
            )
        return httpx.Response(404, json={"error": {"message": "unknown route"}})

    def _response(
        self,
        status: int,
        *,
        body_json: Any,
        body_text: str | None,
    ) -> httpx.Response:
        headers = {}
        if status in {301, 302, 303, 307, 308}:
            headers["Location"] = self.redirect_location
        if body_text is not None:
            return httpx.Response(status, text=body_text, headers=headers)
        if 200 <= status < 300 and body_json is None:
            return httpx.Response(status, headers=headers)
        if not (200 <= status < 300):
            if not isinstance(body_json, dict):
                body_json = {"error": {"message": "gmail error"}}
            return httpx.Response(status, json=body_json, headers=headers)
        return httpx.Response(status, json=body_json, headers=headers)

    def profile_requests(self) -> list[httpx.Request]:
        return [
            request
            for request in self.requests
            if request.method == "GET" and request.url.path == GMAIL_PROFILE_PATH
        ]

    def metadata_requests(self) -> list[httpx.Request]:
        return [
            request
            for request in self.requests
            if request.method == "GET" and request.url.path != GMAIL_PROFILE_PATH
        ]

    def send_requests(self) -> list[httpx.Request]:
        return [request for request in self.requests if request.method == "POST"]


def _is_metadata_path(path: str) -> bool:
    return path.startswith(GMAIL_API_PREFIX) and path != GMAIL_SEND_PATH


def header(name: str, value: str) -> dict[str, str]:
    return {"name": name, "value": value}


def metadata_resource(
    *,
    provider_message_id: str = PROVIDER_MESSAGE_ID,
    thread_id: str = THREAD_ID,
    sender: str = FROM_ADDRESS,
    reply_to: str | None = None,
    subject: str = SUBJECT,
    rfc_message_id: str = RFC_MESSAGE_ID,
    references: str | None = None,
    extra_headers: list[dict[str, str]] | None = None,
    headers: list[dict[str, str]] | None = None,
    snippet: str | None = None,
) -> dict[str, Any]:
    if headers is None:
        headers = [
            header("From", sender),
            header("Subject", subject),
            header("Message-ID", rfc_message_id),
        ]
        if reply_to is not None:
            headers.append(header("Reply-To", reply_to))
        if references is not None:
            headers.append(header("References", references))
        if extra_headers:
            headers.extend(extra_headers)
    payload: dict[str, Any] = {
        "id": provider_message_id,
        "threadId": thread_id,
        "payload": {"mimeType": "text/plain", "headers": headers},
    }
    if snippet is not None:
        payload["snippet"] = snippet
    return payload


def execution_command(**overrides: object) -> CommunicationActionExecution:
    payload: dict[str, object] = {
        "action_id": uuid4(),
        "action_type": WorkflowActionType.REPLY,
        "approved_reply_body": APPROVED_REPLY,
        "connector_account_id": uuid4(),
        "provider_message_id": PROVIDER_MESSAGE_ID,
        "provider": "gmail",
    }
    payload.update(overrides)
    return CommunicationActionExecution.model_validate(payload)


def decoded_provider_message_id(request: httpx.Request) -> str:
    raw_path = request.url.raw_path.decode("ascii").split("?", 1)[0]
    encoded = raw_path[len(GMAIL_API_PREFIX) :]
    return unquote(encoded)


def send_payload(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)


def decoded_rfc_message(request: httpx.Request) -> EmailMessage:
    raw = send_payload(request)["raw"]
    padded = raw + "=" * ((4 - len(raw) % 4) % 4)
    rfc_bytes = base64.urlsafe_b64decode(padded)
    parsed = message_from_bytes(rfc_bytes, policy=SMTP)
    assert isinstance(parsed, EmailMessage)
    return parsed


def mailbox_of(header_value: str | None) -> str:
    assert header_value is not None
    _display, address = parseaddr(header_value)
    return address.strip()


def gmail_executor(
    *,
    stub: GmailReplyHttpStub,
    token: object = GMAIL_TOKEN,
    follow_redirects: bool = False,
) -> tuple[GmailCommunicationActionExecutor, CountingTokenProvider, httpx.Client]:
    token_provider = CountingTokenProvider(token)
    client = httpx.Client(
        transport=httpx.MockTransport(stub),
        follow_redirects=follow_redirects,
    )
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
    )
    return executor, token_provider, client


@pytest.fixture
def gmail_reply_stub() -> GmailReplyHttpStub:
    return GmailReplyHttpStub()


@pytest.fixture
def gmail_reply_executor(
    gmail_reply_stub: GmailReplyHttpStub,
) -> Iterator[
    tuple[
        GmailCommunicationActionExecutor,
        GmailReplyHttpStub,
        httpx.Client,
        CountingTokenProvider,
    ]
]:
    executor, token_provider, client = gmail_executor(stub=gmail_reply_stub)
    try:
        yield executor, gmail_reply_stub, client, token_provider
    finally:
        client.close()
