"""Unit tests for ProviderCommunicationActionExecutorFactory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.domain.enums import ConnectorAccountStatus
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.infrastructure.credentials.environment import (
    EnvironmentCommunicationCredentialResolver,
)
from app.infrastructure.executors.factory import ProviderCommunicationActionExecutorFactory
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
from app.infrastructure.executors.microsoft_graph import (
    MicrosoftGraphCommunicationActionExecutor,
)

_SECRET_REF = "SECRET-CREDENTIAL-REF-FACTORY-123"
_SECRET_TOKEN = "SUPER_SECRET_FACTORY_TOKEN_123"
_GMAIL_ENV = "ECI_COMMUNICATION_CREDENTIAL_GMAIL_SECRET_CREDENTIAL_REF_FACTORY_123_ACCESS_TOKEN"
_GRAPH_ENV = (
    "ECI_COMMUNICATION_CREDENTIAL_MICROSOFT_GRAPH_SECRET_CREDENTIAL_REF_FACTORY_123_ACCESS_TOKEN"
)


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
) -> ConnectorAccountRecord:
    now = datetime.now(UTC)
    return ConnectorAccountRecord(
        id=uuid4(),
        user_id=uuid4(),
        provider=provider,
        external_account_id="opaque-mailbox-locator-not-email",
        credential_ref=credential_ref,
        status=ConnectorAccountStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )


def _factory(
    *,
    environ: dict[str, str] | None = None,
    transport: _CountingTransport | None = None,
) -> tuple[
    ProviderCommunicationActionExecutorFactory,
    _CountingResolver,
    _CountingTransport,
    httpx.Client,
]:
    transport = transport or _CountingTransport()
    resolver = _CountingResolver(
        EnvironmentCommunicationCredentialResolver(environ=environ or {}),
    )
    client = httpx.Client(transport=httpx.MockTransport(transport))
    factory = ProviderCommunicationActionExecutorFactory(
        credential_resolver=resolver,
        http_client=client,
    )
    return factory, resolver, transport, client


def test_gmail_account_with_valid_locator_returns_gmail_executor() -> None:
    factory, resolver, transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        executor = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert isinstance(executor, GmailCommunicationActionExecutor)
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_graph_account_with_valid_locator_returns_graph_executor() -> None:
    factory, resolver, transport, client = _factory(
        environ={_GRAPH_ENV: _SECRET_TOKEN},
    )
    try:
        executor = factory.create_for_account(
            _account(provider="microsoft_graph", credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert isinstance(executor, MicrosoftGraphCommunicationActionExecutor)
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 0
    assert transport.calls == 0


@pytest.mark.parametrize(
    "credential_ref",
    [None, "", "   "],
)
def test_missing_or_blank_credential_ref_is_non_executable(credential_ref: str | None) -> None:
    factory, resolver, transport, client = _factory()
    try:
        executor = factory.create_for_account(
            _account(provider="gmail", credential_ref=credential_ref),
        )
    finally:
        client.close()

    assert executor is None
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_malformed_locator_is_non_executable() -> None:
    factory, resolver, transport, client = _factory()
    try:
        executor = factory.create_for_account(
            _account(provider="gmail", credential_ref="not_a_valid_locator"),
        )
    finally:
        client.close()

    assert executor is None
    assert resolver.resolve_calls == 1
    assert resolver.token_calls == 0
    assert transport.calls == 0


@pytest.mark.parametrize("provider", ["fake", "outlook", "unknown", "Gmail"])
def test_unsupported_provider_is_non_executable(provider: str) -> None:
    factory, resolver, transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        executor = factory.create_for_account(
            _account(provider=provider, credential_ref=_SECRET_REF),
        )
    finally:
        client.close()

    assert executor is None
    assert resolver.resolve_calls == 0
    assert resolver.token_calls == 0
    assert transport.calls == 0


def test_factory_does_not_log_credential_ref_or_token(log_events: list[dict]) -> None:
    factory, _resolver, _transport, client = _factory(
        environ={_GMAIL_ENV: _SECRET_TOKEN},
    )
    try:
        executor = factory.create_for_account(
            _account(provider="gmail", credential_ref=_SECRET_REF),
        )
        missing = factory.create_for_account(
            _account(provider="gmail", credential_ref="not_a_valid_locator"),
        )
    finally:
        client.close()

    assert executor is not None
    assert missing is None
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


def test_unexpected_resolver_error_is_non_executable(
    log_events: list[dict],
) -> None:
    marker = "SECRET_CREDENTIAL_REF_12E"

    class _BoomResolver:
        def resolve(self, *, credential_ref: str, provider: str):
            raise RuntimeError(
                f"{marker} env=ECI_COMMUNICATION_CREDENTIAL_GMAIL_SECRET_ACCESS_TOKEN"
            )

    transport = _CountingTransport()
    client = httpx.Client(transport=httpx.MockTransport(transport))
    factory = ProviderCommunicationActionExecutorFactory(
        credential_resolver=_BoomResolver(),
        http_client=client,
    )
    try:
        executor = factory.create_for_account(
            _account(provider="gmail", credential_ref=marker),
        )
    finally:
        client.close()

    assert executor is None
    assert transport.calls == 0
    serialized = repr(log_events)
    assert marker not in serialized
    assert "ECI_COMMUNICATION_CREDENTIAL" not in serialized
    assert "SECRET_ACCESS_TOKEN" not in serialized


def test_phase12f_credential_ref_marker_is_absent_from_factory_logs(
    log_events: list[dict],
) -> None:
    marker = "SUPER_SECRET_PHASE12_CREDENTIAL_REF"
    factory, resolver, transport, client = _factory()
    try:
        executor = factory.create_for_account(
            _account(provider="gmail", credential_ref=marker),
        )
    finally:
        client.close()

    assert executor is None
    assert resolver.token_calls == 0
    assert transport.calls == 0
    serialized = repr(log_events)
    assert marker not in serialized
    assert "SUPER_SECRET_PHASE12_TOKEN" not in serialized
    assert "credential_ref" not in serialized.lower()
