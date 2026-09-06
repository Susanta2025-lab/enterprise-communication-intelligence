"""HTTP tests for metadata-only attachment listing."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_attachment_scanner,
    get_communication_action_executor_factory,
    get_communication_connector_factory,
    get_token_validator,
    get_unit_of_work_factory,
)
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.security import COMMUNICATIONS_READ_PERMISSION, AuthenticatedPrincipal
from app.domain.enums import AttachmentDisposition, CommunicationCapability
from app.domain.interfaces.communication_action_executor_factory import (
    CommunicationActionExecutorFactory,
)
from app.domain.models import AttachmentMetadata
from app.infrastructure.attachments.fake_scanner import FakeAttachmentScanner
from app.infrastructure.connectors.fake import FakeCommunicationConnector
from app.main import create_app
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


class _ForbiddenExecutorFactory(CommunicationActionExecutorFactory):
    def create_for_account(self, account):  # noqa: ANN001
        raise AssertionError("attachment metadata listing must not construct a write executor")

_LIST = "/api/v1/connector-accounts/{connector_account_id}/messages/attachments"
_ANALYZE = "/api/v1/connector-accounts/{connector_account_id}/messages/attachments/analyze"
_SETTINGS_ENV_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "APP_ENV",
    "AUTH_MODE",
    "OIDC_ISSUER",
    "OIDC_AUDIENCE",
    "OIDC_JWKS_URL",
    "OIDC_REQUIRED_PERMISSION",
    "AI_PROVIDER",
    "ATTACHMENT_SCANNER_BACKEND",
    "DATABASE_URL",
)


class _CountingConnector(FakeCommunicationConnector):
    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.list_attachment_calls: list[str] = []
        self.fetch_content_calls: list[tuple[str, str]] = []

    def list_attachments(self, provider_message_id: str):
        self.list_attachment_calls.append(provider_message_id)
        return super().list_attachments(provider_message_id)

    def fetch_attachment_content(self, provider_message_id: str, provider_attachment_id: str):
        self.fetch_content_calls.append((provider_message_id, provider_attachment_id))
        return super().fetch_attachment_content(provider_message_id, provider_attachment_id)


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[tuple[TestClient, InMemoryUnitOfWork, _CountingConnector]]:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("OIDC_REQUIRED_PERMISSION", TEST_PERMISSION)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    metadata = AttachmentMetadata(
        provider_attachment_id="att-1",
        filename="Contract.pdf",
        media_type="application/pdf",
        reported_size=1887436,
        is_inline=False,
        disposition=AttachmentDisposition.ATTACHMENT,
    )
    connector = _CountingConnector(attachments={"fake-msg-001": (metadata,)})
    factory = StaticCommunicationConnectorFactory(connector)
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(unit)
    application.dependency_overrides[get_communication_connector_factory] = lambda: factory
    application.dependency_overrides[get_attachment_scanner] = lambda: FakeAttachmentScanner()
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    with TestClient(application) as test_client:
        yield test_client, unit, connector


def _token(private_key, scp: str) -> str:
    return encode_test_token(private_key, extra_claims={"scp": scp})


def _seed_owner(unit: InMemoryUnitOfWork):
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION, COMMUNICATIONS_READ_PERMISSION}),
    )
    return IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)


def test_unauthenticated_attachment_list_returns_401(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
) -> None:
    client, _unit, connector = api
    response = client.get(
        _LIST.format(connector_account_id=uuid4()),
        params={"provider_message_id": "fake-msg-001"},
    )
    assert response.status_code == 401
    assert connector.list_attachment_calls == []
    assert connector.fetch_content_calls == []


def test_analyze_permission_is_not_required_for_metadata(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    response = client.get(
        _LIST.format(connector_account_id=account.id),
        params={"provider_message_id": "fake-msg-001"},
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["truncated"] is False
    assert payload["items"][0]["filename"] == "Contract.pdf"
    assert payload["items"][0]["reported_size"] == 1887436
    assert "content_id" not in payload["items"][0]
    assert connector.list_attachment_calls == ["fake-msg-001"]
    assert connector.fetch_content_calls == []


def test_metadata_list_does_not_call_analyze_or_content_fetch(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    listed = client.get(
        _LIST.format(connector_account_id=account.id),
        params={"provider_message_id": "fake-msg-001"},
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert listed.status_code == 200
    assert connector.fetch_content_calls == []
    analyze = client.post(
        _ANALYZE.format(connector_account_id=account.id),
        json={"provider_message_id": "fake-msg-001", "provider_attachment_id": "att-1"},
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert analyze.status_code == 403
    assert connector.fetch_content_calls == []


def test_unknown_message_returns_404_without_content_fetch(
    api: tuple[TestClient, InMemoryUnitOfWork, _CountingConnector],
    private_key,
) -> None:
    client, unit, connector = api
    owner_id = _seed_owner(unit)
    account = sample_connector_account(
        owner_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    response = client.get(
        _LIST.format(connector_account_id=account.id),
        params={"provider_message_id": "missing-msg"},
        headers=bearer_header(_token(private_key, COMMUNICATIONS_READ_PERMISSION)),
    )
    assert response.status_code == 404
    assert connector.fetch_content_calls == []
