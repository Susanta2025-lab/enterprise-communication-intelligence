"""Unit tests for Microsoft Graph reply HTTP behavior and request contract."""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx
import pytest
from pydantic import ValidationError

from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
    ServiceUnavailableError,
)
from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor
from app.infrastructure.credentials import EnvironmentCommunicationCredentialResolver
from app.infrastructure.executors.microsoft_graph import MicrosoftGraphCommunicationActionExecutor
from tests.unit.infrastructure.executors.microsoft_graph.conftest import (
    APPROVED_REPLY,
    GRAPH_REPLY_PREFIX,
    GRAPH_REPLY_SUFFIX,
    GRAPH_TOKEN,
    PROVIDER_MESSAGE_ID,
    CountingTokenProvider,
    GraphReplyHttpStub,
    decoded_message_id,
    execution_command,
)

_GRAPH_ENV = "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_GRAPH_TEST_ACCESS_TOKEN"
_RESOLVER_TOKEN = "fake-graph-write-token"


def test_graph_executor_implements_write_port(graph_reply_executor: tuple) -> None:
    executor, _stub, _client, _tokens = graph_reply_executor

    assert isinstance(executor, CommunicationActionExecutor)
    assert not hasattr(executor, "list_messages")
    assert not hasattr(executor, "fetch_message")
    assert not hasattr(executor, "send")
    assert not hasattr(executor, "reply")


def test_reply_posts_native_graph_url_with_json_comment(
    graph_reply_executor: tuple,
) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    command = execution_command()

    result = executor.execute(command)

    assert result is None
    assert tokens.calls == 1
    assert len(stub.requests) == 1
    request = stub.requests[0]
    assert request.method == "POST"
    assert request.url.scheme == "https"
    assert request.url.host == "graph.microsoft.com"
    raw_path = request.url.raw_path.decode("ascii")
    encoded_id = quote(PROVIDER_MESSAGE_ID, safe="")
    assert raw_path == f"{GRAPH_REPLY_PREFIX}{encoded_id}{GRAPH_REPLY_SUFFIX}"
    assert request.headers.get("authorization") == f"Bearer {GRAPH_TOKEN}"
    assert "authorization" not in str(request.url).lower()
    assert not request.url.query
    content_type = request.headers.get("content-type", "")
    assert "application/json" in content_type.lower()
    assert json.loads(request.content) == {"comment": APPROVED_REPLY}


def test_success_does_not_require_response_body(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.body_text = ""

    result = executor.execute(execution_command())

    assert result is None
    assert len(stub.requests) == 1


def test_success_ignores_synthetic_202_body(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    stub.body_json = {"id": "should-not-be-parsed", "internetMessageId": "<secret@example.com>"}

    result = executor.execute(execution_command())

    assert result is None
    assert len(stub.requests) == 1


def test_approved_reply_body_is_the_exact_comment(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    approved = "Authorized snapshot, not the proposed draft."
    command = execution_command(approved_reply_body=approved)

    executor.execute(command)

    assert json.loads(stub.requests[0].content) == {"comment": approved}


def test_special_character_body_is_preserved_as_json(graph_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    approved = 'He said "done".\nNext line — café 😀'
    command = execution_command(approved_reply_body=approved)

    executor.execute(command)

    payload = json.loads(stub.requests[0].content)
    assert payload == {"comment": approved}
    assert payload["comment"] == approved


def test_reserved_characters_in_message_id_cannot_alter_reply_path(
    graph_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    malicious_id = "msg/id?x=1#https://evil.example/steal%frag"
    command = execution_command(provider_message_id=malicious_id)

    executor.execute(command)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    encoded_id = quote(malicious_id, safe="")
    assert request.url.scheme == "https"
    assert request.url.host == "graph.microsoft.com"
    assert raw_path == f"{GRAPH_REPLY_PREFIX}{encoded_id}{GRAPH_REPLY_SUFFIX}"
    assert raw_path.startswith(GRAPH_REPLY_PREFIX)
    assert raw_path.endswith(GRAPH_REPLY_SUFFIX)
    assert "%2F" in raw_path.upper()
    assert "%3F" in raw_path.upper()
    assert "%23" in raw_path.upper()
    assert "%25" in raw_path.upper()
    assert request.url.fragment == ""
    assert request.url.params.get("x") is None
    assert decoded_message_id(request) == malicious_id
    assert "/steal" not in raw_path


def test_percent_encoded_message_id_is_encoded_again_not_decoded(
    graph_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = graph_reply_executor
    encoded_looking_id = "AAMkAGI2%2FTAAA="
    command = execution_command(provider_message_id=encoded_looking_id)

    executor.execute(command)

    request = stub.requests[0]
    raw_path = request.url.raw_path.decode("ascii")
    encoded_id = quote(encoded_looking_id, safe="")
    assert raw_path == f"{GRAPH_REPLY_PREFIX}{encoded_id}{GRAPH_REPLY_SUFFIX}"
    assert "%252F" in raw_path.upper()
    assert raw_path.count("/") == GRAPH_REPLY_PREFIX.count("/") + GRAPH_REPLY_SUFFIX.count("/")
    assert decoded_message_id(request) == encoded_looking_id


def test_execution_command_rejects_blank_provider_message_id() -> None:
    with pytest.raises(ValidationError):
        execution_command(provider_message_id="")
    with pytest.raises(ValidationError):
        execution_command(provider_message_id="   ")


def test_execution_command_rejects_blank_approved_reply_body() -> None:
    with pytest.raises(ValidationError):
        execution_command(approved_reply_body="")
    with pytest.raises(ValidationError):
        execution_command(approved_reply_body="   ")


def test_token_provider_is_invoked_on_execute(graph_reply_executor: tuple) -> None:
    executor, _stub, _client, tokens = graph_reply_executor
    assert tokens.calls == 0

    executor.execute(execution_command())

    assert tokens.calls == 1


def test_provider_gmail_rejects_before_token_or_http(graph_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    command = execution_command(provider="gmail")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    assert exc_info.value.message == "Communication action execution failed."
    assert exc_info.value.__cause__ is None


def test_provider_fake_rejects_before_token_or_http(graph_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    command = execution_command(provider="fake")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    assert "fake" not in exc_info.value.message.lower()


def test_provider_unknown_rejects_before_token_or_http(graph_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    command = execution_command(provider="unknown_mailbox")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    assert "unknown" not in exc_info.value.message.lower()


def test_provider_casing_is_strict(graph_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    command = execution_command(provider="Microsoft_Graph")

    with pytest.raises(CommunicationActionExecutionError):
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []


def test_non_reply_action_rejects_before_token_or_http(graph_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = graph_reply_executor
    payload = execution_command().model_dump()
    payload["action_type"] = "forward"
    unsupported = CommunicationActionExecution.model_construct(**payload)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(unsupported)

    assert tokens.calls == 0
    assert stub.requests == []
    assert exc_info.value.message == "Communication action execution failed."
    assert "forward" not in exc_info.value.message.lower()


def test_executor_does_not_close_injected_client(graph_reply_executor: tuple) -> None:
    executor, stub, client, _tokens = graph_reply_executor

    executor.execute(execution_command())

    assert len(stub.requests) == 1
    assert not client.is_closed


def test_environment_resolver_composes_with_graph_executor() -> None:
    stub = GraphReplyHttpStub()
    resolver = EnvironmentCommunicationCredentialResolver(
        environ={_GRAPH_ENV: _RESOLVER_TOKEN},
    )
    token_provider = resolver.resolve(
        credential_ref="graph-test",
        provider="microsoft_graph",
    )
    client = httpx.Client(transport=httpx.MockTransport(stub))
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
    )
    try:
        result = executor.execute(execution_command())
    finally:
        client.close()

    assert result is None
    assert len(stub.requests) == 1
    assert stub.requests[0].headers.get("authorization") == f"Bearer {_RESOLVER_TOKEN}"
    assert json.loads(stub.requests[0].content) == {"comment": APPROVED_REPLY}


def test_empty_token_is_unavailable_before_http(graph_reply_executor: tuple) -> None:
    _executor, stub, client, _tokens = graph_reply_executor
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(""),
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert exc_info.value.message == "Communication action execution is currently unavailable."
    assert exc_info.value.__cause__ is None


def test_whitespace_token_is_unavailable_before_http(graph_reply_executor: tuple) -> None:
    _executor, stub, client, _tokens = graph_reply_executor
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider("   "),
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)


def test_token_provider_exception_is_unavailable_before_http(
    graph_reply_executor: tuple,
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor

    def boom() -> str:
        raise RuntimeError("token store exploded")

    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=boom,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "token store exploded" not in exc_info.value.message
    assert exc_info.value.__cause__ is None


def test_credential_unavailable_is_unavailable_before_http(
    graph_reply_executor: tuple,
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor

    def missing_token() -> str:
        raise CommunicationCredentialUnavailableError()

    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=missing_token,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "credential" not in exc_info.value.message.lower()
    assert exc_info.value.__cause__ is None


def test_reauthorization_required_propagates_before_http(
    graph_reply_executor: tuple,
) -> None:
    _executor, stub, client, _tokens = graph_reply_executor

    def permanent_failure() -> str:
        raise CommunicationCredentialReauthorizationRequiredError()

    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=permanent_failure,
    )

    with pytest.raises(CommunicationCredentialReauthorizationRequiredError):
        executor.execute(execution_command())

    assert stub.requests == []


def test_environment_resolver_missing_token_is_unavailable_before_http() -> None:
    stub = GraphReplyHttpStub()
    resolver = EnvironmentCommunicationCredentialResolver(environ={})
    token_provider = resolver.resolve(
        credential_ref="graph-test",
        provider="microsoft_graph",
    )
    client = httpx.Client(transport=httpx.MockTransport(stub))
    executor = MicrosoftGraphCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
    )
    try:
        with pytest.raises(ServiceUnavailableError) as exc_info:
            executor.execute(execution_command())
    finally:
        client.close()

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "graph-test" not in exc_info.value.message
    assert "ECI_COMMUNICATION_CREDENTIAL" not in exc_info.value.message
