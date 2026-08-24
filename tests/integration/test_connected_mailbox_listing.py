"""HTTP tests for connected-mailbox message listing."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_ai_provider,
    get_communication_action_executor_factory,
    get_communication_connector_factory,
    get_mailbox_read_credential_resolver,
    get_mailbox_read_http_client,
    get_token_validator,
    get_unit_of_work_factory,
)
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.exceptions import (
    CommunicationCredentialReauthorizationRequiredError,
    CommunicationCredentialUnavailableError,
)
from app.core.security import (
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.infrastructure.connectors.microsoft_graph.pagination import (
    opaque_cursor_from_next_link,
)
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.main import create_app
from app.providers.mock.provider import MockAIProvider
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_connector_account,
)
from tests.support.jwt_tokens import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_JWKS_URL,
    TEST_PERMISSION,
    TEST_SUBJECT,
    bearer_header,
    encode_test_token,
    generate_test_rsa_private_key,
    make_test_validator,
)
from tests.unit.infrastructure.connectors.gmail.conftest import (
    GMAIL_TOKEN,
    GmailHttpStub,
    gmail_resource,
)
from tests.unit.infrastructure.connectors.microsoft_graph.conftest import (
    GRAPH_TOKEN,
    GraphHttpStub,
    graph_resource,
)

_LIST_URL = "/api/v1/connector-accounts/{connector_account_id}/messages"
_ANALYZE_URL = "/api/v1/connector-accounts/{connector_account_id}/messages/analyze"
_DIRECT_ANALYZE = "/api/v1/communications/analyze"
_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "LOG_LEVEL",
    "API_V1_PREFIX",
    "AI_PROVIDER",
    "FOUNDRY_PROJECT_ENDPOINT",
    "FOUNDRY_MODEL_DEPLOYMENT",
    "BEDROCK_REGION",
    "BEDROCK_MODEL_ID",
    "AUTH_MODE",
    "OIDC_ISSUER",
    "OIDC_AUDIENCE",
    "OIDC_JWKS_URL",
    "OIDC_REQUIRED_PERMISSION",
    "DATABASE_URL",
)
_READ_ANALYZE = f"{COMMUNICATIONS_READ_PERMISSION} {TEST_PERMISSION}"
_GMAIL_LOCATOR = "mailbox-gmail-1"
_GRAPH_LOCATOR = "mailbox-graph-1"
_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_MAILBOX_GMAIL_1_ACCESS_TOKEN"
_GRAPH_ENV = (
    "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_MAILBOX_GRAPH_1_ACCESS_TOKEN"
)
_GRAPH_NEXT_LINK = (
    "https://graph.microsoft.com/v1.0/me/messages"
    "?$select=id&$top=1&$skiptoken=graph-page-2"
)
_LIST_ITEM_FIELDS = {
    "provider_message_id",
    "sender",
    "subject",
    "sent_at",
    "received_at",
}


class _CountingResolver:
    def __init__(self, inner: EnvironmentCommunicationCredentialResolver) -> None:
        self.inner = inner
        self.resolve_calls = 0
        self.token_calls = 0

    def resolve(self, *, credential_ref: str, provider: str):
        self.resolve_calls += 1
        token_provider = self.inner.resolve(
            credential_ref=credential_ref,
            provider=provider,
        )

        def counted() -> str:
            self.token_calls += 1
            return token_provider()

        return counted


class _ForbiddenExecutorFactory(CommunicationActionExecutorFactory):
    def create_for_account(self, account):  # noqa: ANN001
        raise AssertionError("mailbox listing must not construct a write executor")


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _enable_oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("OIDC_REQUIRED_PERMISSION", TEST_PERMISSION)


def _token(private_key, scp: str, *, subject: str = TEST_SUBJECT) -> str:
    return encode_test_token(
        private_key,
        subject=subject,
        extra_claims={"scp": scp},
    )


def _seed_owner(unit: InMemoryUnitOfWork, *, subject: str = TEST_SUBJECT) -> object:
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION, COMMUNICATIONS_READ_PERMISSION}),
    )
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)


def _assert_public_item(item: dict) -> None:
    assert set(item) == _LIST_ITEM_FIELDS
    assert item["provider_message_id"]
    assert item["sender"]
    serialized = repr(item)
    assert "body" not in item
    assert "html" not in serialized.lower()
    assert "recipients" not in item
    assert "thread_id" not in item
    assert "credential_ref" not in serialized
    assert "access_token" not in serialized
    assert "@odata.nextLink" not in serialized
    assert "graph.microsoft.com" not in serialized


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def mailbox_client(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory]]:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    factory = StaticCommunicationConnectorFactory(FakeCommunicationConnector())
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = lambda: factory
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    with TestClient(application) as test_client:
        yield test_client, unit, factory


def test_unauthenticated_mailbox_list_returns_401(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
) -> None:
    client, _unit, factory = mailbox_client
    response = client.get(_LIST_URL.format(connector_account_id=uuid4()))
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert factory.calls == 0


def test_auth_disabled_mailbox_list_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    application = create_app()
    with TestClient(application) as client:
        response = client.get(_LIST_URL.format(connector_account_id=uuid4()))
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize(
    "scp",
    [
        TEST_PERMISSION,
        COMMUNICATIONS_CONNECT_PERMISSION,
        COMMUNICATIONS_SEND_PERMISSION,
        COMMUNICATIONS_WORKFLOW_PERMISSION,
        f"{TEST_PERMISSION} {COMMUNICATIONS_CONNECT_PERMISSION}",
    ],
)
def test_missing_read_permission_returns_403(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
    scp: str,
) -> None:
    client, _unit, factory = mailbox_client
    response = client.get(
        _LIST_URL.format(connector_account_id=uuid4()),
        headers=bearer_header(_token(private_key, scp)),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    assert factory.calls == 0


def test_read_only_and_read_plus_analyze_are_authorized(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
) -> None:
    client, unit, factory = mailbox_client
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    url = _LIST_URL.format(connector_account_id=account.id)

    read_only = client.get(
        url,
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    both = client.get(
        url,
        headers=bearer_header(_token(private_key, _READ_ANALYZE)),
    )

    assert read_only.status_code == 200
    assert both.status_code == 200
    assert factory.calls == 2
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({}, 200),
        ({"page_size": 1}, 200),
        ({"page_size": 100}, 200),
        ({"page_size": 101}, 422),
        ({"page_size": 0}, 422),
        ({"page_size": -1}, 422),
        ({"cursor": "n:1"}, 200),
        ({"nextLink": "https://graph.microsoft.com/v1.0/me/messages"}, 422),
        ({"credential_ref": "secret"}, 422),
    ],
)
def test_list_query_validation(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
    params: dict,
    status: int,
) -> None:
    client, unit, _factory = mailbox_client
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    response = client.get(
        _LIST_URL.format(connector_account_id=account.id),
        params=params,
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert response.status_code == status
    if status == 200 and not params:
        assert len(response.json()["items"]) == 5
    if status == 200 and params.get("page_size") == 1:
        assert len(response.json()["items"]) == 1
        assert response.json()["next_cursor"] == "n:1"


def test_owned_account_lists_and_unknown_or_foreign_are_identical_404(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
) -> None:
    client, unit, factory = mailbox_client
    owner_id = _seed_owner(unit)
    other_id = _seed_owner(unit, subject="other-subject")
    owned = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    foreign = sample_connector_account(
        other_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[owned.id] = owned
    unit.connector_account_store[foreign.id] = foreign
    headers = bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION))

    success = client.get(
        _LIST_URL.format(connector_account_id=owned.id),
        params={"page_size": 2},
        headers=headers,
    )
    unknown = client.get(
        _LIST_URL.format(connector_account_id=uuid4()),
        headers=headers,
    )
    cross = client.get(
        _LIST_URL.format(connector_account_id=foreign.id),
        headers=headers,
    )

    assert success.status_code == 200
    payload = success.json()
    assert set(payload) == {"items", "next_cursor"}
    assert payload["next_cursor"] == "n:2"
    assert len(payload["items"]) == 2
    _assert_public_item(payload["items"][0])
    assert unknown.status_code == 404
    assert cross.status_code == 404
    assert unknown.json() == cross.json() == {"detail": "Connector account not found."}
    assert factory.calls == 1
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}
    serialized = repr(payload)
    assert "Please review the Q3 budget proposal before Friday." not in serialized


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": ConnectorAccountStatus.DISCONNECTED},
        {"status": ConnectorAccountStatus.REAUTH_REQUIRED},
        {"granted_capabilities": (CommunicationCapability.MAIL_SEND,)},
        {"granted_capabilities": ()},
        {"credential_ref": None},
        {"provider": "fake"},
    ],
)
def test_unusable_owned_account_returns_409_before_factory(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
    kwargs: dict,
) -> None:
    client, unit, factory = mailbox_client
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider=kwargs.get("provider", "gmail"),
        status=kwargs.get("status", ConnectorAccountStatus.ACTIVE),
        granted_capabilities=kwargs.get(
            "granted_capabilities",
            (CommunicationCapability.MAIL_READ,),
        ),
        credential_ref=kwargs.get("credential_ref", "mailbox-locator-001"),
    )
    unit.connector_account_store[account.id] = account
    response = client.get(
        _LIST_URL.format(connector_account_id=account.id),
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Connected mailbox is not available."}
    assert factory.calls == 0


def test_legacy_null_capabilities_remain_eligible(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
) -> None:
    client, unit, factory = mailbox_client
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=None,
    )
    unit.connector_account_store[account.id] = account
    response = client.get(
        _LIST_URL.format(connector_account_id=account.id),
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert response.status_code == 200
    assert factory.calls == 1


def test_invalid_cursor_returns_400(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
) -> None:
    client, unit, factory = mailbox_client
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    response = client.get(
        _LIST_URL.format(connector_account_id=account.id),
        params={"cursor": "gmail-page-token"},
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox pagination cursor is invalid."}
    assert factory.calls == 1


def test_analyze_still_requires_read_and_analyze(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
) -> None:
    client, unit, _factory = mailbox_client
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    read_only = client.post(
        _ANALYZE_URL.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001"},
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    both = client.post(
        _ANALYZE_URL.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001"},
        headers=bearer_header(_token(private_key, _READ_ANALYZE)),
    )
    assert read_only.status_code == 403
    assert both.status_code == 200
    assert both.json()["analysis"]["summary"]["text"]


def test_direct_text_analyze_stays_analyze_only(
    mailbox_client: tuple[TestClient, InMemoryUnitOfWork, StaticCommunicationConnectorFactory],
    private_key,
) -> None:
    client, _unit, factory = mailbox_client
    payload = {
        "message": {
            "body": "Sharing the notes from today's standup for visibility.",
            "message_id": "direct-msg-001",
            "metadata": {
                "source_type": "email",
                "sender": "alice@example.com",
                "recipients": ["bob@example.com"],
                "subject": "Standup notes",
            },
        }
    }
    analyze_only = client.post(
        _DIRECT_ANALYZE,
        json=payload,
        headers=bearer_header(_token(private_key, TEST_PERMISSION)),
    )
    read_only = client.post(
        _DIRECT_ANALYZE,
        json=payload,
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert analyze_only.status_code == 200
    assert read_only.status_code == 403
    assert factory.calls == 0


def test_gmail_path_lists_bounded_page(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailHttpStub()
    stub.messages["gmail-msg-1"] = gmail_resource(
        "gmail-msg-1",
        body="Please review the attached contract before Thursday.",
        subject="Contract review",
    )
    stub.list_ids = ["gmail-msg-1"]
    stub.next_page_token = "gmail-page-2"
    resolver = _CountingResolver(
        EnvironmentCommunicationCredentialResolver(environ={_GMAIL_ENV: GMAIL_TOKEN}),
    )
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        credential_ref=_GMAIL_LOCATOR,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    validator = make_test_validator(private_key)
    http_client = httpx.Client(transport=httpx.MockTransport(stub))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)

    def _http_client():
        yield http_client

    application.dependency_overrides[get_mailbox_read_http_client] = _http_client
    application.dependency_overrides[get_mailbox_read_credential_resolver] = lambda: resolver
    provider = MagicMock(wraps=MockAIProvider())
    application.dependency_overrides[get_ai_provider] = lambda: provider
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    try:
        with TestClient(application) as client:
            assert resolver.token_calls == 0
            first = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                params={"page_size": 1},
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
            stub.list_ids = []
            stub.next_page_token = None
            second = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                params={"page_size": 1, "cursor": first.json()["next_cursor"]},
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
    finally:
        http_client.close()

    assert first.status_code == 200
    body = first.json()
    assert body["next_cursor"] == "gmail-page-2"
    _assert_public_item(body["items"][0])
    assert body["items"][0]["provider_message_id"] == "gmail-msg-1"
    assert body["items"][0]["subject"] == "Contract review"
    assert "Please review the attached contract before Thursday." not in repr(body)
    assert second.status_code == 200
    assert second.json()["next_cursor"] is None
    assert stub.requests[0].url.params.get("maxResults") == "1"
    assert stub.requests[0].url.params.get("pageToken") is None
    continuation = next(
        request
        for request in stub.requests
        if request.url.params.get("pageToken") == "gmail-page-2"
    )
    assert continuation.url.params.get("maxResults") == "1"
    assert resolver.token_calls >= 1
    assert provider.analyze.call_count == 0
    assert unit.analyses == {}
    assert unit.workflow_action_store == {}


def test_graph_path_hides_next_link(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GraphHttpStub()
    stub.messages["graph-msg-1"] = graph_resource(
        "graph-msg-1",
        body="Please confirm the invoice payment by Monday.",
        subject="Invoice confirmation",
    )
    stub.list_ids = ["graph-msg-1"]
    stub.next_link = _GRAPH_NEXT_LINK
    resolver = _CountingResolver(
        EnvironmentCommunicationCredentialResolver(environ={_GRAPH_ENV: GRAPH_TOKEN}),
    )
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="microsoft_graph",
        credential_ref=_GRAPH_LOCATOR,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    validator = make_test_validator(private_key)
    http_client = httpx.Client(transport=httpx.MockTransport(stub))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)

    def _http_client():
        yield http_client

    application.dependency_overrides[get_mailbox_read_http_client] = _http_client
    application.dependency_overrides[get_mailbox_read_credential_resolver] = lambda: resolver
    provider = MagicMock(wraps=MockAIProvider())
    application.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        with TestClient(application) as client:
            first = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                params={"page_size": 1},
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
            stub.list_ids = []
            stub.next_link = None
            second = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                params={"page_size": 1, "cursor": first.json()["next_cursor"]},
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
    finally:
        http_client.close()

    assert first.status_code == 200
    payload = first.json()
    expected_cursor = opaque_cursor_from_next_link(_GRAPH_NEXT_LINK)
    assert payload["next_cursor"] == expected_cursor
    assert "graph.microsoft.com" not in repr(payload)
    assert "@odata.nextLink" not in repr(payload)
    assert _GRAPH_NEXT_LINK not in repr(payload)
    _assert_public_item(payload["items"][0])
    assert payload["items"][0]["provider_message_id"] == "graph-msg-1"
    assert "Please confirm the invoice payment by Monday." not in repr(payload)
    assert second.status_code == 200
    assert second.json()["next_cursor"] is None
    assert stub.requests[0].url.params.get("$top") == "1"
    continuation = next(
        request
        for request in stub.requests
        if request.url.params.get("$skiptoken") == "graph-page-2"
    )
    assert continuation.url.host == "graph.microsoft.com"
    assert continuation.url.params.get("$top") == "1"
    assert continuation.url.params.get("$select") == "id"
    assert provider.analyze.call_count == 0


def test_permanent_refresh_failure_returns_409_without_mailbox_http(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailHttpStub()
    stub.messages["gmail-msg-1"] = gmail_resource("gmail-msg-1")

    class _ReauthResolver:
        resolve_calls = 0
        token_calls = 0

        def resolve(self, *, credential_ref: str, provider: str):
            self.resolve_calls += 1

            def _token() -> str:
                self.token_calls += 1
                raise CommunicationCredentialReauthorizationRequiredError()

            return _token

    resolver = _ReauthResolver()
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        credential_ref=_GMAIL_LOCATOR,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    validator = make_test_validator(private_key)
    http_client = httpx.Client(transport=httpx.MockTransport(stub))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)

    def _http_client():
        yield http_client

    application.dependency_overrides[get_mailbox_read_http_client] = _http_client
    application.dependency_overrides[get_mailbox_read_credential_resolver] = lambda: resolver
    provider = MagicMock(wraps=MockAIProvider())
    application.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        with TestClient(application) as client:
            response = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
    finally:
        http_client.close()
    assert response.status_code == 409
    assert response.json() == {"detail": "Connected mailbox is not available."}
    assert resolver.token_calls == 1
    assert stub.requests == []
    assert provider.analyze.call_count == 0
    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert stored.credential_ref == _GMAIL_LOCATOR
    assert stored.granted_capabilities == (CommunicationCapability.MAIL_READ,)
    assert stored.external_account_id == account.external_account_id
    assert _GMAIL_LOCATOR not in response.text
    with TestClient(application) as client:
        follow_up = client.get(
            _LIST_URL.format(connector_account_id=account.id),
            headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
        )
    assert follow_up.status_code == 409
    assert resolver.token_calls == 1
    assert stub.requests == []


def test_transient_token_failure_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailHttpStub()

    class _TransientResolver:
        def resolve(self, *, credential_ref: str, provider: str):
            def _token() -> str:
                raise CommunicationCredentialUnavailableError()

            return _token

    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        credential_ref=_GMAIL_LOCATOR,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    validator = make_test_validator(private_key)
    http_client = httpx.Client(transport=httpx.MockTransport(stub))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)

    def _http_client():
        yield http_client

    application.dependency_overrides[get_mailbox_read_http_client] = _http_client
    application.dependency_overrides[get_mailbox_read_credential_resolver] = (
        lambda: _TransientResolver()
    )
    provider = MagicMock(wraps=MockAIProvider())
    application.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        with TestClient(application) as client:
            response = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
    finally:
        http_client.close()
    assert response.status_code == 503
    assert provider.analyze.call_count == 0
    assert stub.requests == []
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_mailbox_http_401_keeps_account_active(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailHttpStub()
    stub.list_status = 401
    stub.error_json = {"error": {"message": "SECRET_PROVIDER_PAYLOAD"}}
    resolver = _CountingResolver(
        EnvironmentCommunicationCredentialResolver(environ={_GMAIL_ENV: GMAIL_TOKEN}),
    )
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        credential_ref=_GMAIL_LOCATOR,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    validator = make_test_validator(private_key)
    http_client = httpx.Client(transport=httpx.MockTransport(stub))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)

    def _http_client():
        yield http_client

    application.dependency_overrides[get_mailbox_read_http_client] = _http_client
    application.dependency_overrides[get_mailbox_read_credential_resolver] = lambda: resolver
    provider = MagicMock(wraps=MockAIProvider())
    application.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        with TestClient(application) as client:
            response = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
    finally:
        http_client.close()
    assert response.status_code == 503
    assert resolver.token_calls == 1
    assert stub.requests
    assert provider.analyze.call_count == 0
    stored = unit.connector_account_store[account.id]
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert stored.credential_ref == _GMAIL_LOCATOR
    assert "SECRET_PROVIDER_PAYLOAD" not in response.text
    assert GMAIL_TOKEN not in response.text


def test_connector_timeout_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    stub = GmailHttpStub()
    stub.transport_error = httpx.TimeoutException("timed out")
    resolver = _CountingResolver(
        EnvironmentCommunicationCredentialResolver(environ={_GMAIL_ENV: GMAIL_TOKEN}),
    )
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        credential_ref=_GMAIL_LOCATOR,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    validator = make_test_validator(private_key)
    http_client = httpx.Client(transport=httpx.MockTransport(stub))
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)

    def _http_client():
        yield http_client

    application.dependency_overrides[get_mailbox_read_http_client] = _http_client
    application.dependency_overrides[get_mailbox_read_credential_resolver] = lambda: resolver
    provider = MagicMock(wraps=MockAIProvider())
    application.dependency_overrides[get_ai_provider] = lambda: provider
    try:
        with TestClient(application) as client:
            response = client.get(
                _LIST_URL.format(connector_account_id=account.id),
                headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
            )
    finally:
        http_client.close()
    assert response.status_code == 503
    assert provider.analyze.call_count == 0
