"""Unit tests for ProviderCommunicationConnectorFactory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.core.exceptions import CommunicationConnectorNotAvailableError
from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces import CommunicationActionExecutor, CommunicationConnector
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.connectors.factory import ProviderCommunicationConnectorFactory
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from app.infrastructure.connectors.microsoft_graph import (
    MicrosoftGraphCommunicationConnector,
)
from app.infrastructure.credentials.composite import CompositeCommunicationCredentialResolver
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.credentials.oauth import OAuthCommunicationCredentialResolver
from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory
from tests.unit.infrastructure.credentials.conftest import (
    CountingStore,
    FakeRefreshAdapter,
    seed_credential,
)

_SECRET_REF = "SECRET-CREDENTIAL-REF-FACTORY-123"
_SECRET_TOKEN = "SUPER_SECRET_FACTORY_TOKEN_123"
_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_SECRET_CREDENTIAL_REF_FACTORY_123_ACCESS_TOKEN"
_GRAPH_ENV = (
    "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_SECRET_CREDENTIAL_REF_FACTORY_123_ACCESS_TOKEN"
)
_OAUTH_LOCATOR = "oauth-readfactory0001"


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


class _CountingTransport:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(599, json={"error": "factory must not call HTTP"})


def _account(
    *,
    provider: str,
    credential_ref: str | None = "demo-account",
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
) -> ConnectorAccountRecord:
    now = datetime.now(UTC)
    return ConnectorAccountRecord(
        id=uuid4(),
        user_id=uuid4(),
        provider=provider,
        external_account_id="opaque-mailbox-locator-not-email",
        credential_ref=credential_ref,
        status=status,
        created_at=now,
        updated_at=now,
    )


def _factory(
    *,
    environ: dict[str, str] | None = None,
    transport: _CountingTransport | None = None,
    resolver: object | None = None,
) -> tuple[
    ProviderCommunicationConnectorFactory,
    object,
    _CountingTransport,
    httpx.Client,
]:
    transport = transport or _CountingTransport()
    if resolver is None:
        resolver = _CountingResolver(
            EnvironmentCommunicationCredentialResolver(environ=environ or {}),
        )
    client = httpx.Client(transport=httpx.MockTransport(transport))
    factory = ProviderCommunicationConnectorFactory(
        credential_resolver=resolver,
        http_client=client,
    )
    return factory, resolver, transport, client


def test_gmail_account_routes_to_gmail_connector_without_token_or_http() -> None:
    factory, resolver, transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        connector = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert isinstance(connector, GmailCommunicationConnector)
    assert isinstance(connector, CommunicationConnector)
    assert not isinstance(connector, CommunicationActionExecutor)
    assert not hasattr(connector, "send")
    assert not hasattr(connector, "reply")
    assert not hasattr(connector, "execute")
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_graph_account_routes_to_graph_connector_without_token_or_http() -> None:
    factory, resolver, transport, client = _factory(
        environ={_GRAPH_ENV: _SECRET_TOKEN},
    )
    try:
        connector = factory.create_for_account(
            _account(provider="microsoft_graph", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert isinstance(connector, MicrosoftGraphCommunicationConnector)
    assert isinstance(connector, CommunicationConnector)
    assert not isinstance(connector, CommunicationActionExecutor)
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 0
    assert transport.calls == 0


@pytest.mark.parametrize(
    "credential_ref",
    [None, "", "   "],
)
def test_missing_or_blank_credential_ref_is_not_available(
    credential_ref: str | None,
) -> None:
    factory, resolver, transport, client = _factory()
    try:
        with pytest.raises(CommunicationConnectorNotAvailableError) as exc_info:
            factory.create_for_account(
                _account(provider="gmail", credential_ref=credential_ref),
            )
    finally:
        client.close()

    assert "gmail" not in exc_info.value.message.lower()
    assert "credential_ref" not in exc_info.value.message.lower()
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_malformed_locator_is_not_available() -> None:
    factory, resolver, transport, client = _factory()
    try:
        with pytest.raises(CommunicationConnectorNotAvailableError) as exc_info:
            factory.create_for_account(
                _account(provider="gmail", credential_ref="not_a_valid_locator"),
            )
    finally:
        client.close()

    assert "not_a_valid_locator" not in exc_info.value.message
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 0
    assert transport.calls == 0


@pytest.mark.parametrize("provider", ["fake", "outlook", "unknown", "Gmail"])
def test_unsupported_provider_is_not_available_without_io(provider: str) -> None:
    factory, resolver, transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        with pytest.raises(CommunicationConnectorNotAvailableError) as exc_info:
            factory.create_for_account(
                _account(provider=provider, credential_ref=_SECRET_REF),
            )
    finally:
        client.close()

    lowered = exc_info.value.message.lower()
    assert "gmail" not in lowered
    assert "graph" not in lowered
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_oauth_locator_routes_through_oauth_resolver_lazily() -> None:
    store = CountingStore()
    seed_credential(store, locator=_OAUTH_LOCATOR)
    adapter = FakeRefreshAdapter(token="oauth-access-token")
    oauth = OAuthCommunicationCredentialResolver(store, {"gmail": adapter})
    environment = EnvironmentCommunicationCredentialResolver(environ={})
    resolver = CompositeCommunicationCredentialResolver(
        oauth_resolver=oauth,
        environment_resolver=environment,
    )
    transport = _CountingTransport()
    client = httpx.Client(transport=httpx.MockTransport(transport))
    factory = ProviderCommunicationConnectorFactory(
        credential_resolver=resolver,
        http_client=client,
    )
    try:
        connector = factory.create_for_account(
            _account(provider="gmail", credential_ref=_OAUTH_LOCATOR),
        )
    finally:
        client.close()

    assert isinstance(connector, GmailCommunicationConnector)
    assert store.gets == 0
    assert adapter.calls == []
    assert transport.calls == 0


def test_legacy_locator_preserves_environment_resolver() -> None:
    store = CountingStore()
    adapter = FakeRefreshAdapter(token="oauth-must-not-be-used")
    oauth = OAuthCommunicationCredentialResolver(store, {"gmail": adapter})
    environment = EnvironmentCommunicationCredentialResolver(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    resolver = CompositeCommunicationCredentialResolver(
        oauth_resolver=oauth,
        environment_resolver=environment,
    )
    transport = _CountingTransport()
    client = httpx.Client(transport=httpx.MockTransport(transport))
    factory = ProviderCommunicationConnectorFactory(
        credential_resolver=resolver,
        http_client=client,
    )
    try:
        connector = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert isinstance(connector, GmailCommunicationConnector)
    assert store.gets == 0
    assert adapter.calls == []
    assert transport.calls == 0


def test_disconnected_account_is_still_routable_by_factory() -> None:
    factory, resolver, transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        connector = factory.create_for_account(
            _account(
                provider="gmail",
                credential_ref=_SECRET_REF,
                status=ConnectorAccountStatus.DISCONNECTED,
            ),
        )
    finally:
        client.close()

    assert isinstance(connector, GmailCommunicationConnector)
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_read_factory_is_not_the_write_factory() -> None:
    read_factory, _resolver, _transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    write_factory = ProviderCommunicationActionExecutorFactory(
        credential_resolver=_resolver,
        http_client=client,
    )
    try:
        connector = read_factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
        executor = write_factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert isinstance(connector, CommunicationConnector)
    assert isinstance(executor, CommunicationActionExecutor)
    assert type(read_factory) is not type(write_factory)
    assert not hasattr(CommunicationConnector, "send")
    assert not hasattr(CommunicationConnector, "reply")
    assert not hasattr(CommunicationConnector, "execute")


def test_factory_does_not_log_credential_ref_or_token(log_events: list[dict]) -> None:
    factory, _resolver, _transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        connector = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
        with pytest.raises(CommunicationConnectorNotAvailableError):
            factory.create_for_account(
                _account(provider="gmail", credential_ref="not_a_valid_locator"),
            )
    finally:
        client.close()

    assert connector is not None
    serialized = repr(log_events)
    assert _SECRET_REF not in serialized
    assert _SECRET_TOKEN not in serialized
    assert _GMAIL_ENV not in serialized
    assert "credential_ref" not in serialized.lower()


def test_create_for_account_twice_does_not_invoke_token_or_http() -> None:
    factory, resolver, transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        first = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
        second = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert first is not None
    assert second is not None
    assert resolver.resolve_calls == 2
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_unexpected_resolver_error_is_not_available(
    log_events: list[dict],
) -> None:
    marker = "SECRET_CREDENTIAL_REF_14B"

    class _BoomResolver:
        def resolve(self, *, credential_ref: str, provider: str):
            raise RuntimeError(
                f"{marker} env=ECI_COMMUNICATION_CREDENTIAL_GMAIL_SECRET_ACCESS_TOKEN"
            )

    transport = _CountingTransport()
    client = httpx.Client(transport=httpx.MockTransport(transport))
    factory = ProviderCommunicationConnectorFactory(
        credential_resolver=_BoomResolver(),
        http_client=client,
    )
    try:
        with pytest.raises(CommunicationConnectorNotAvailableError):
            factory.create_for_account(
                _account(provider="gmail", credential_ref=marker),
            )
    finally:
        client.close()

    assert transport.calls == 0
    serialized = repr(log_events)
    assert marker not in serialized
    assert "ECI_COMMUNICATION_CREDENTIAL" not in serialized
    assert "SECRET_ACCESS_TOKEN" not in serialized


def test_factory_does_not_encode_ownership_or_lifecycle_policy() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[4]
        / "app"
        / "infrastructure"
        / "connectors"
        / "factory.py"
    ).read_text(encoding="utf-8")
    assert "get_owned" not in source
    assert "is_mail_read_allowed" not in source
    assert "ConnectorAccountStatus" not in source
    assert "mark_reauth_required" not in source
    assert "FakeCommunicationConnector" not in source


def test_static_test_factory_implements_the_read_port() -> None:
    from app.infrastructure.connectors.fake import FakeCommunicationConnector
    from tests.support.connector_factory import StaticCommunicationConnectorFactory

    fake = FakeCommunicationConnector()
    factory = StaticCommunicationConnectorFactory(fake)
    account = _account(provider="gmail", credential_ref=_SECRET_REF)
    connector = factory.create_for_account(account)
    assert connector is fake
    assert factory.calls == 1
    assert factory.accounts == [account]

