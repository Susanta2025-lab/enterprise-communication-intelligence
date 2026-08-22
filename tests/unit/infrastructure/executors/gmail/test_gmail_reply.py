"""Unit tests for Gmail reply HTTP behavior, MIME contract, and threading."""

from __future__ import annotations

from email.utils import getaddresses
from urllib.parse import quote

import httpx
import pytest
from pydantic import ValidationError

from app.core.exceptions import (
    CommunicationActionExecutionError,
    CommunicationCredentialUnavailableError,
    ServiceUnavailableError,
)
from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor
from app.infrastructure.credentials import EnvironmentCommunicationCredentialResolver
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
from tests.unit.infrastructure.executors.gmail.conftest import (
    APPROVED_REPLY,
    FROM_ADDRESS,
    GMAIL_API_PREFIX,
    GMAIL_SEND_PATH,
    GMAIL_TOKEN,
    MAILBOX_ADDRESS,
    PROVIDER_MESSAGE_ID,
    RFC_MESSAGE_ID,
    SUBJECT,
    THREAD_ID,
    CountingTokenProvider,
    GmailReplyHttpStub,
    decoded_provider_message_id,
    decoded_rfc_message,
    execution_command,
    gmail_executor,
    header,
    mailbox_of,
    metadata_resource,
    send_payload,
)

_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_GMAIL_TEST_ACCESS_TOKEN"
_RESOLVER_TOKEN = "fake-gmail-write-token"
_EXPECTED_METADATA_HEADERS = ["From", "Reply-To", "Subject", "Message-ID", "References"]


def test_gmail_executor_implements_write_port(gmail_reply_executor: tuple) -> None:
    executor, _stub, _client, _tokens = gmail_reply_executor

    assert isinstance(executor, CommunicationActionExecutor)
    assert not hasattr(executor, "list_messages")
    assert not hasattr(executor, "fetch_message")
    assert not hasattr(executor, "send")
    assert not hasattr(executor, "reply")


def test_reply_fetches_metadata_then_posts_send(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = gmail_reply_executor

    result = executor.execute(execution_command())

    assert result is None
    assert tokens.calls == 1
    assert len(stub.metadata_requests()) == 1
    assert len(stub.send_requests()) == 1
    metadata_request = stub.metadata_requests()[0]
    send_request = stub.send_requests()[0]
    assert metadata_request.method == "GET"
    assert metadata_request.url.host == "gmail.googleapis.com"
    encoded_id = quote(PROVIDER_MESSAGE_ID, safe="")
    assert metadata_request.url.path == f"{GMAIL_API_PREFIX}{encoded_id}"
    assert metadata_request.url.params.get("format") == "metadata"
    assert metadata_request.url.params.get_list("metadataHeaders") == _EXPECTED_METADATA_HEADERS
    assert metadata_request.headers.get("authorization") == f"Bearer {GMAIL_TOKEN}"
    assert "authorization" not in str(metadata_request.url).lower()
    assert send_request.method == "POST"
    assert send_request.url.path == GMAIL_SEND_PATH
    assert send_request.url.host == "gmail.googleapis.com"
    assert send_request.headers.get("authorization") == f"Bearer {GMAIL_TOKEN}"
    assert not send_request.url.query
    payload = send_payload(send_request)
    assert set(payload) == {"raw", "threadId"}
    assert payload["threadId"] == THREAD_ID


def test_metadata_fetch_does_not_request_full_or_raw(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor

    executor.execute(execution_command())

    params = stub.metadata_requests()[0].url.params
    assert params.get("format") == "metadata"
    assert "full" not in params.get_list("format")
    assert "raw" not in params.get_list("format")
    assert "minimal" not in params.get_list("format")
    assert "To" not in params.get_list("metadataHeaders")
    assert "Cc" not in params.get_list("metadataHeaders")
    assert "Bcc" not in params.get_list("metadataHeaders")


def test_raw_is_urlsafe_base64_of_entire_rfc_message(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor

    executor.execute(execution_command())

    raw = send_payload(stub.send_requests()[0])["raw"]
    assert isinstance(raw, str)
    assert "+" not in raw
    assert "/" not in raw
    alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
    assert set(raw.rstrip("=")) <= alphabet
    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert parsed["From"] is not None
    assert parsed.get_content_type() == "text/plain"


def test_decoded_mime_uses_trusted_from_and_approved_body(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert mailbox_of(parsed["From"]) == MAILBOX_ADDRESS
    assert mailbox_of(parsed["To"]) == FROM_ADDRESS
    assert parsed["Subject"] == SUBJECT
    assert RFC_MESSAGE_ID.strip("<>") in (parsed["In-Reply-To"] or "")
    assert RFC_MESSAGE_ID.strip("<>") in (parsed["References"] or "")
    assert parsed.get_content().strip() == APPROVED_REPLY
    assert parsed.get("Cc") is None
    assert parsed.get("Bcc") is None
    assert parsed.get_content_maintype() == "text"
    assert parsed.get_content_subtype() == "plain"
    assert not parsed.is_multipart()


def test_reply_to_overrides_from(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(reply_to="replies@example.test")

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert mailbox_of(parsed["To"]) == "replies@example.test"
    assert mailbox_of(parsed["From"]) == MAILBOX_ADDRESS


def test_from_is_used_when_reply_to_is_absent(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(sender="Finance Bot <finance.bot@example.test>")

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert mailbox_of(parsed["To"]) == "finance.bot@example.test"


def test_original_cc_and_bcc_are_not_copied(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        extra_headers=[
            header("To", "owner@example.test, other@example.test"),
            header("Cc", "manager@example.test"),
            header("Bcc", "hidden@example.test"),
        ]
    )

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    recipients = [address for _display, address in getaddresses([parsed["To"] or ""])]
    assert recipients == [FROM_ADDRESS]
    assert parsed.get("Cc") is None
    assert parsed.get("Bcc") is None


def test_subject_is_preserved_without_prepending_re(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(subject="Budget review")

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert parsed["Subject"] == "Budget review"
    assert parsed["Subject"] is not None
    assert not parsed["Subject"].startswith("Re:")


def test_existing_re_subject_is_not_rewritten(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(subject="Re: Budget review")

    executor.execute(execution_command())

    assert decoded_rfc_message(stub.send_requests()[0])["Subject"] == "Re: Budget review"


def test_references_use_message_id_when_chain_is_absent(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource()

    executor.execute(execution_command())

    references = decoded_rfc_message(stub.send_requests()[0])["References"] or ""
    assert RFC_MESSAGE_ID.strip("<>") in references
    assert references.count(RFC_MESSAGE_ID.strip("<>")) == 1


def test_references_preserve_existing_chain(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    chain = "<a@test> <b@test>"
    stub.metadata_json = metadata_resource(
        references=chain,
        rfc_message_id="<c@test>",
    )

    executor.execute(execution_command())

    references = decoded_rfc_message(stub.send_requests()[0])["References"] or ""
    assert references.split() == ["<a@test>", "<b@test>", "<c@test>"]


def test_references_do_not_duplicate_trailing_message_id(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        references="<a@test> <c@test>",
        rfc_message_id="<c@test>",
    )

    executor.execute(execution_command())

    references = decoded_rfc_message(stub.send_requests()[0])["References"] or ""
    assert references.split() == ["<a@test>", "<c@test>"]
    assert references.count("<c@test>") == 1


def test_references_preserve_earlier_duplicate_parent(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(
        references="<c@test> <a@test>",
        rfc_message_id="<c@test>",
    )

    executor.execute(execution_command())

    references = decoded_rfc_message(stub.send_requests()[0])["References"] or ""
    assert references.split() == ["<c@test>", "<a@test>", "<c@test>"]


def test_unicode_subject_is_preserved_without_rewriting(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    subject = "Café — Q3 预算"

    stub.metadata_json = metadata_resource(subject=subject)
    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert parsed["Subject"] == subject
    assert not (parsed["Subject"] or "").startswith("Re:")


def test_display_name_from_is_parsed_to_one_mailbox(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.metadata_json = metadata_resource(sender="Alice Example <alice@example.test>")

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert mailbox_of(parsed["To"]) == "alice@example.test"
    assert parsed.get("Cc") is None
    assert parsed.get("Bcc") is None


def test_emailmessage_header_error_is_translated_before_send(
    gmail_reply_executor: tuple,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email.errors import HeaderParseError
    from email.message import EmailMessage

    executor, stub, _client, _tokens = gmail_reply_executor

    def boom(self: EmailMessage, name: str, val: object) -> None:
        raise HeaderParseError("malformed header")

    monkeypatch.setattr(EmailMessage, "__setitem__", boom)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(execution_command())

    assert stub.send_requests() == []
    assert len(stub.metadata_requests()) == 1
    assert exc_info.value.message == "Communication action execution failed."
    assert exc_info.value.__cause__ is None
    blob = f"{exc_info.value.message}{exc_info.value}{exc_info.value!r}"
    assert "HeaderParseError" not in blob
    assert "malformed header" not in blob


def test_unicode_approved_body_is_preserved(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    approved = 'He said "done".\nNext line — café 😀'

    executor.execute(execution_command(approved_reply_body=approved))

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert parsed.get_content().replace("\r\n", "\n").strip() == approved
    assert parsed.get_content_type() == "text/plain"


def test_approved_body_is_not_semantically_rewritten(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    approved = "Authorized snapshot, not the proposed draft."

    executor.execute(execution_command(approved_reply_body=approved))

    body = decoded_rfc_message(stub.send_requests()[0]).get_content()
    assert "proposed" not in body.lower() or "Authorized snapshot" in body
    assert body.strip() == approved


def test_body_cannot_inject_mime_headers(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    approved = "Please ignore.\nBcc: victim@example.test\nTo: other@example.test"

    executor.execute(execution_command(approved_reply_body=approved))

    parsed = decoded_rfc_message(stub.send_requests()[0])
    assert parsed.get("Bcc") is None
    assert mailbox_of(parsed["To"]) == FROM_ADDRESS
    assert "victim@example.test" in parsed.get_content()


def test_snippet_and_payload_body_are_not_quoted(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    original = "ORIGINAL_GMAIL_BODY_SHOULD_NOT_APPEAR"
    stub.metadata_json = metadata_resource(snippet=original)
    stub.metadata_json["payload"]["body"] = {"data": "c2VjcmV0"}
    stub.metadata_json["payload"]["parts"] = [
        {"mimeType": "text/plain", "body": {"data": "c2VjcmV0"}}
    ]

    executor.execute(execution_command())

    parsed = decoded_rfc_message(stub.send_requests()[0])
    body = parsed.get_content()
    assert original not in body
    assert "On " not in body
    assert not body.lstrip().startswith(">")
    assert body.strip() == APPROVED_REPLY


def test_success_does_not_require_response_body(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_text = ""
    stub.send_json = None

    result = executor.execute(execution_command())

    assert result is None
    assert len(stub.send_requests()) == 1


def test_success_ignores_synthetic_message_json(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_json = {"id": "should-not-be-parsed", "threadId": "secret-thread", "raw": "secret"}

    result = executor.execute(execution_command())

    assert result is None
    assert len(stub.send_requests()) == 1


def test_success_ignores_malformed_json_body(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    stub.send_text = "{not-json"

    result = executor.execute(execution_command())

    assert result is None
    assert len(stub.send_requests()) == 1


def test_reserved_characters_in_message_id_cannot_alter_metadata_path(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    malicious_id = "msg/id?x=1#https://evil.example/steal%frag"
    stub.metadata_json = metadata_resource(provider_message_id=malicious_id)

    executor.execute(execution_command(provider_message_id=malicious_id))

    request = stub.metadata_requests()[0]
    raw_path = request.url.raw_path.decode("ascii")
    path_only = raw_path.split("?", 1)[0]
    encoded_id = quote(malicious_id, safe="")
    assert request.url.scheme == "https"
    assert request.url.host == "gmail.googleapis.com"
    assert path_only == f"{GMAIL_API_PREFIX}{encoded_id}"
    assert "%2F" in path_only.upper()
    assert "%3F" in path_only.upper()
    assert "%23" in path_only.upper()
    assert "%25" in path_only.upper()
    assert request.url.fragment == ""
    assert decoded_provider_message_id(request) == malicious_id
    assert "/steal" not in path_only


def test_percent_encoded_message_id_is_encoded_again_not_decoded(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, _tokens = gmail_reply_executor
    encoded_looking_id = "abc%2Fdef"
    stub.metadata_json = metadata_resource(provider_message_id=encoded_looking_id)

    executor.execute(execution_command(provider_message_id=encoded_looking_id))

    request = stub.metadata_requests()[0]
    raw_path = request.url.raw_path.decode("ascii")
    path_only = raw_path.split("?", 1)[0]
    encoded_id = quote(encoded_looking_id, safe="")
    assert path_only == f"{GMAIL_API_PREFIX}{encoded_id}"
    assert "%252F" in path_only.upper()
    assert decoded_provider_message_id(request) == encoded_looking_id


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


def test_constructor_rejects_blank_mailbox_address(gmail_reply_stub: GmailReplyHttpStub) -> None:
    client = httpx.Client(transport=httpx.MockTransport(gmail_reply_stub))
    try:
        with pytest.raises(ValueError) as exc_info:
            GmailCommunicationActionExecutor(
                http_client=client,
                access_token_provider=CountingTokenProvider(),
                mailbox_address="   ",
            )
    finally:
        client.close()
    assert "owner@" not in str(exc_info.value)
    assert gmail_reply_stub.requests == []


def test_constructor_rejects_multiple_mailbox_addresses(
    gmail_reply_stub: GmailReplyHttpStub,
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(gmail_reply_stub))
    try:
        with pytest.raises(ValueError) as exc_info:
            GmailCommunicationActionExecutor(
                http_client=client,
                access_token_provider=CountingTokenProvider(),
                mailbox_address="owner@example.test, other@example.test",
            )
    finally:
        client.close()
    assert "owner@example.test" not in str(exc_info.value)
    assert gmail_reply_stub.requests == []


def test_constructor_rejects_header_injection_in_mailbox(
    gmail_reply_stub: GmailReplyHttpStub,
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(gmail_reply_stub))
    try:
        with pytest.raises(ValueError):
            GmailCommunicationActionExecutor(
                http_client=client,
                access_token_provider=CountingTokenProvider(),
                mailbox_address="owner@example.test\r\nBcc: victim@example.test",
            )
    finally:
        client.close()
    assert gmail_reply_stub.requests == []


def test_constructor_rejects_malformed_mailbox_address(
    gmail_reply_stub: GmailReplyHttpStub,
) -> None:
    client = httpx.Client(transport=httpx.MockTransport(gmail_reply_stub))
    try:
        with pytest.raises(ValueError):
            GmailCommunicationActionExecutor(
                http_client=client,
                access_token_provider=CountingTokenProvider(),
                mailbox_address="not-a-mailbox",
            )
    finally:
        client.close()
    assert gmail_reply_stub.requests == []


def test_constructor_rejects_empty_mailbox_address(gmail_reply_stub: GmailReplyHttpStub) -> None:
    client = httpx.Client(transport=httpx.MockTransport(gmail_reply_stub))
    try:
        with pytest.raises(ValueError):
            GmailCommunicationActionExecutor(
                http_client=client,
                access_token_provider=CountingTokenProvider(),
                mailbox_address="",
            )
    finally:
        client.close()
    assert gmail_reply_stub.requests == []


def test_constructor_rejects_group_mailbox_syntax(gmail_reply_stub: GmailReplyHttpStub) -> None:
    client = httpx.Client(transport=httpx.MockTransport(gmail_reply_stub))
    try:
        with pytest.raises(ValueError):
            GmailCommunicationActionExecutor(
                http_client=client,
                access_token_provider=CountingTokenProvider(),
                mailbox_address="Owners: owner@example.test;",
            )
    finally:
        client.close()
    assert gmail_reply_stub.requests == []


def test_token_provider_is_invoked_once_on_execute(gmail_reply_executor: tuple) -> None:
    executor, _stub, _client, tokens = gmail_reply_executor
    assert tokens.calls == 0

    executor.execute(execution_command())

    assert tokens.calls == 1


def test_provider_microsoft_graph_rejects_before_token_or_http(
    gmail_reply_executor: tuple,
) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    command = execution_command(provider="microsoft_graph")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    assert exc_info.value.message == "Communication action execution failed."
    assert exc_info.value.__cause__ is None


def test_provider_fake_rejects_before_token_or_http(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    command = execution_command(provider="fake")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    assert "fake" not in exc_info.value.message.lower()


def test_provider_unknown_rejects_before_token_or_http(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    command = execution_command(provider="unknown_mailbox")

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []
    assert "unknown" not in exc_info.value.message.lower()


def test_provider_casing_is_strict(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    command = execution_command(provider="Gmail")

    with pytest.raises(CommunicationActionExecutionError):
        executor.execute(command)

    assert tokens.calls == 0
    assert stub.requests == []


def test_non_reply_action_rejects_before_token_or_http(gmail_reply_executor: tuple) -> None:
    executor, stub, _client, tokens = gmail_reply_executor
    payload = execution_command().model_dump()
    payload["action_type"] = "forward"
    unsupported = CommunicationActionExecution.model_construct(**payload)

    with pytest.raises(CommunicationActionExecutionError) as exc_info:
        executor.execute(unsupported)

    assert tokens.calls == 0
    assert stub.requests == []
    assert exc_info.value.message == "Communication action execution failed."
    assert "forward" not in exc_info.value.message.lower()


def test_executor_does_not_close_injected_client(gmail_reply_executor: tuple) -> None:
    executor, stub, client, _tokens = gmail_reply_executor

    executor.execute(execution_command())

    assert len(stub.send_requests()) == 1
    assert not client.is_closed


def test_environment_resolver_composes_with_gmail_executor() -> None:
    stub = GmailReplyHttpStub()
    resolver = EnvironmentCommunicationCredentialResolver(
        environ={_GMAIL_ENV: _RESOLVER_TOKEN},
    )
    token_provider = resolver.resolve(
        credential_ref="gmail-test",
        provider="gmail",
    )
    client = httpx.Client(transport=httpx.MockTransport(stub))
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
        mailbox_address=MAILBOX_ADDRESS,
    )
    try:
        result = executor.execute(execution_command())
    finally:
        client.close()

    assert result is None
    assert len(stub.metadata_requests()) == 1
    assert len(stub.send_requests()) == 1
    assert stub.metadata_requests()[0].headers.get("authorization") == f"Bearer {_RESOLVER_TOKEN}"
    assert stub.send_requests()[0].headers.get("authorization") == f"Bearer {_RESOLVER_TOKEN}"
    assert send_payload(stub.send_requests()[0])["threadId"] == THREAD_ID


def test_empty_token_is_unavailable_before_http(gmail_reply_executor: tuple) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider(""),
        mailbox_address=MAILBOX_ADDRESS,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert exc_info.value.message == "Communication action execution is currently unavailable."
    assert exc_info.value.__cause__ is None


def test_whitespace_token_is_unavailable_before_http(gmail_reply_executor: tuple) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=CountingTokenProvider("   "),
        mailbox_address=MAILBOX_ADDRESS,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)


def test_token_provider_exception_is_unavailable_before_http(
    gmail_reply_executor: tuple,
) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor

    def boom() -> str:
        raise RuntimeError("token store exploded")

    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=boom,
        mailbox_address=MAILBOX_ADDRESS,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "token store exploded" not in exc_info.value.message
    assert exc_info.value.__cause__ is None


def test_credential_unavailable_is_unavailable_before_http(
    gmail_reply_executor: tuple,
) -> None:
    _executor, stub, client, _tokens = gmail_reply_executor

    def missing_token() -> str:
        raise CommunicationCredentialUnavailableError()

    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=missing_token,
        mailbox_address=MAILBOX_ADDRESS,
    )

    with pytest.raises(ServiceUnavailableError) as exc_info:
        executor.execute(execution_command())

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "credential" not in exc_info.value.message.lower()
    assert exc_info.value.__cause__ is None


def test_environment_resolver_missing_token_is_unavailable_before_http() -> None:
    stub = GmailReplyHttpStub()
    resolver = EnvironmentCommunicationCredentialResolver(environ={})
    token_provider = resolver.resolve(
        credential_ref="gmail-test",
        provider="gmail",
    )
    client = httpx.Client(transport=httpx.MockTransport(stub))
    executor = GmailCommunicationActionExecutor(
        http_client=client,
        access_token_provider=token_provider,
        mailbox_address=MAILBOX_ADDRESS,
    )
    try:
        with pytest.raises(ServiceUnavailableError) as exc_info:
            executor.execute(execution_command())
    finally:
        client.close()

    assert stub.requests == []
    assert not isinstance(exc_info.value, CommunicationActionExecutionError)
    assert "gmail-test" not in exc_info.value.message
    assert "ECI_COMMUNICATION_CREDENTIAL" not in exc_info.value.message


def test_redirect_is_not_followed_on_metadata_when_client_would_follow(
    gmail_reply_stub: GmailReplyHttpStub,
) -> None:
    gmail_reply_stub.metadata_status = 302
    executor, tokens, client = gmail_executor(stub=gmail_reply_stub, follow_redirects=True)
    try:
        with pytest.raises(CommunicationActionExecutionError) as exc_info:
            executor.execute(execution_command())
        assert len(gmail_reply_stub.requests) == 1
        assert gmail_reply_stub.requests[0].url.host == "gmail.googleapis.com"
        assert all(request.url.host != "evil.example" for request in gmail_reply_stub.requests)
        assert gmail_reply_stub.send_requests() == []
        authorization = gmail_reply_stub.requests[0].headers.get("authorization")
        assert authorization is not None
        assert "evil.example" not in authorization
        assert tokens.calls == 1
        assert "gmail" not in exc_info.value.message.lower()
    finally:
        client.close()


def test_redirect_is_not_followed_on_send_when_client_would_follow(
    gmail_reply_stub: GmailReplyHttpStub,
) -> None:
    gmail_reply_stub.send_status = 302
    executor, _tokens, client = gmail_executor(stub=gmail_reply_stub, follow_redirects=True)
    try:
        with pytest.raises(CommunicationActionExecutionError) as exc_info:
            executor.execute(execution_command())
        assert len(gmail_reply_stub.metadata_requests()) == 1
        assert len(gmail_reply_stub.send_requests()) == 1
        assert all(request.url.host != "evil.example" for request in gmail_reply_stub.requests)
        send_auth = gmail_reply_stub.send_requests()[0].headers.get("authorization")
        assert send_auth is not None
        assert "evil.example" not in send_auth
        assert "gmail" not in exc_info.value.message.lower()
    finally:
        client.close()
