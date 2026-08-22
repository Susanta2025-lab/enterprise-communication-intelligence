"""Shared Microsoft Graph reply-executor fixtures for mocked httpx tests."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

import httpx
import pytest

from app.domain.enums import WorkflowActionType
from app.domain.interfaces import CommunicationActionExecution
from app.infrastructure.executors.microsoft_graph import MicrosoftGraphCommunicationActionExecutor

GRAPH_TOKEN = "unit-test-graph-token"
GRAPH_REPLY_PREFIX = "/v1.0/me/messages/"
GRAPH_REPLY_SUFFIX = "/reply"
APPROVED_REPLY = "Thanks, I will review the report and respond by Friday."
PROVIDER_MESSAGE_ID = "AAMkAGI2TAAA="


class CountingTokenProvider:
    """On-demand token callable that records how many times it was invoked."""

    def __init__(self, token: object = GRAPH_TOKEN) -> None:
        self.calls = 0
        self.token = token

    def __call__(self) -> str:
        self.calls += 1
        return self.token  # type: ignore[return-value]


class GraphReplyHttpStub:
    """Scripted Microsoft Graph reply surface backed by httpx.MockTransport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 202
        self.body_json: Any = None
        self.body_text: str | None = None
        self.error_json: dict[str, Any] | None = None
        self.transport_error: BaseException | None = None
        self.redirect_location = "https://evil.example/steal"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.transport_error is not None:
            raise self.transport_error
        raw_path = request.url.raw_path.decode("ascii")
        if request.method != "POST" or not _is_reply_path(raw_path):
            return httpx.Response(
                404,
                json={"error": {"code": "Unknown", "message": "unknown route"}},
            )
        headers = {}
        if self.status in {301, 302, 303, 307, 308}:
            headers["Location"] = self.redirect_location
        if self.body_text is not None:
            return httpx.Response(self.status, text=self.body_text, headers=headers)
        if self.body_json is not None:
            return httpx.Response(self.status, json=self.body_json, headers=headers)
        if self.status == 202:
            return httpx.Response(202, headers=headers)
        body = self.error_json or {"error": {"code": "Error", "message": "graph error"}}
        return httpx.Response(self.status, json=body, headers=headers)


def _is_reply_path(raw_path: str) -> bool:
    return raw_path.startswith(GRAPH_REPLY_PREFIX) and raw_path.endswith(GRAPH_REPLY_SUFFIX)


def decoded_message_id(request: httpx.Request) -> str:
    raw_path = request.url.raw_path.decode("ascii")
    encoded = raw_path[len(GRAPH_REPLY_PREFIX) : -len(GRAPH_REPLY_SUFFIX)]
    return unquote(encoded)


def execution_command(**overrides: object) -> CommunicationActionExecution:
    payload: dict[str, object] = {
        "action_id": uuid4(),
        "action_type": WorkflowActionType.REPLY,
        "approved_reply_body": APPROVED_REPLY,
        "connector_account_id": uuid4(),
        "provider_message_id": PROVIDER_MESSAGE_ID,
        "provider": "microsoft_graph",
    }
    payload.update(overrides)
    return CommunicationActionExecution.model_validate(payload)


@pytest.fixture
def graph_reply_stub() -> GraphReplyHttpStub:
    return GraphReplyHttpStub()


@pytest.fixture
def graph_reply_executor(
    graph_reply_stub: GraphReplyHttpStub,
) -> Iterator[
    tuple[
        MicrosoftGraphCommunicationActionExecutor,
        GraphReplyHttpStub,
        httpx.Client,
        CountingTokenProvider,
    ]
]:
    token_provider = CountingTokenProvider()
    client = httpx.Client(transport=httpx.MockTransport(graph_reply_stub))
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
    )
    try:
        yield executor, graph_reply_stub, client, token_provider
    finally:
        client.close()
