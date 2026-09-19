"""Integration tests for BusinessContext HTTP APIs and authorization."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_ai_provider,
    get_attachment_scanner,
    get_communication_action_executor_factory,
    get_communication_connector_factory,
    get_token_validator,
    get_unit_of_work_factory,
)
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.security import (
    COMMUNICATIONS_READ_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.enums import ApplicationRole, CommunicationCapability
from app.domain.interfaces import CommunicationActionExecutorFactory
from app.domain.interfaces.communication_connector import (
    AttachmentMetadataPage,
    CommunicationConnector,
    ConnectorMessageQuery,
    MessagePage,
)
from app.domain.interfaces.connector_account_repository import ConnectorAccountRecord
from app.domain.models import AttachmentContent, CommunicationMessage
from app.infrastructure.attachments import FakeAttachmentScanner
from app.main import create_app
from app.providers.mock import MockAIProvider
from tests.support.connector_factory import StaticCommunicationConnectorFactory
from tests.support.in_memory_persistence import (
    InMemoryUnitOfWork,
    UnitOfWorkFactory,
    sample_analysis_record,
    sample_connector_account,
)
from tests.support.jwt_tokens import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_JWKS_URL,
    TEST_PERMISSION,
    bearer_header,
    encode_test_token,
    generate_test_rsa_private_key,
    make_test_validator,
)

_CONTEXTS_URL = "/api/v1/contexts"
_SUBJECT_A = "user-a-subject"
_SUBJECT_B = "user-b-subject"
_SUBJECT_OWNER = "platform-owner-subject"
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
_FORBIDDEN_RESPONSE_KEYS = {
    "user_id",
    "owner_user_id",
    "issuer",
    "subject",
    "raw_body",
    "sender",
    "recipient",
    "recipients",
    "email",
    "access_token",
    "refresh_token",
    "Authorization",
    "credential_ref",
}


class _SpyConnector(CommunicationConnector):
    """Mailbox connector that records any accidental provider I/O."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def provider(self) -> str:
        return "spy"

    def list_messages(self, query: ConnectorMessageQuery) -> MessagePage:
        self.calls.append("list_messages")
        raise AssertionError("mailbox list must not run for context APIs")

    def fetch_message(self, provider_message_id: str) -> CommunicationMessage:
        self.calls.append("fetch_message")
        raise AssertionError("mailbox fetch must not run for context APIs")

    def list_attachments(self, provider_message_id: str) -> AttachmentMetadataPage:
        self.calls.append("list_attachments")
        raise AssertionError("attachment list must not run for context APIs")

    def fetch_attachment_content(
        self,
        provider_message_id: str,
        provider_attachment_id: str,
    ) -> AttachmentContent:
        self.calls.append("fetch_attachment_content")
        raise AssertionError("attachment fetch must not run for context APIs")


class _ForbiddenExecutorFactory(CommunicationActionExecutorFactory):
    def create_for_account(self, account: ConnectorAccountRecord):  # noqa: ANN201
        raise AssertionError("workflow executors must not run for context APIs")


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


def _token(private_key, subject: str, *permissions: str) -> str:
    return encode_test_token(
        private_key,
        subject=subject,
        extra_claims={"scp": " ".join(permissions)},
    )


def _headers(private_key, subject: str, *permissions: str) -> dict[str, str]:
    return bearer_header(_token(private_key, subject, *permissions))


def _analyze_headers(private_key, subject: str = _SUBJECT_A) -> dict[str, str]:
    return _headers(private_key, subject, TEST_PERMISSION)


def _read_analyze_headers(private_key, subject: str = _SUBJECT_A) -> dict[str, str]:
    return _headers(
        private_key,
        subject,
        TEST_PERMISSION,
        COMMUNICATIONS_READ_PERMISSION,
    )


def _collect_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(value.keys())
        for item in value.values():
            keys.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_keys(item))
    return keys


def _assert_context_privacy(payload: object) -> None:
    keys = _collect_keys(payload)
    assert keys.isdisjoint(_FORBIDDEN_RESPONSE_KEYS)


def _create_context(
    client: TestClient,
    private_key,
    *,
    subject: str = _SUBJECT_A,
    title: str = "Matter One",
    context_type: str = "matter",
    reference: str | None = None,
) -> dict:
    body: dict[str, Any] = {"type": context_type, "title": title}
    if reference is not None:
        body["reference"] = reference
    response = client.post(
        _CONTEXTS_URL,
        json=body,
        headers=_analyze_headers(private_key, subject),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def api(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[
    tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ]
]:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    spy = _SpyConnector()
    factory = StaticCommunicationConnectorFactory(spy)
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(
        unit
    )
    application.dependency_overrides[get_communication_connector_factory] = (
        lambda: factory
    )
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider()
    application.dependency_overrides[get_attachment_scanner] = (
        lambda: FakeAttachmentScanner()
    )
    application.dependency_overrides[get_communication_action_executor_factory] = (
        lambda: _ForbiddenExecutorFactory()
    )
    with TestClient(application) as test_client:
        yield test_client, unit, spy, factory


def _promote_owner(unit: InMemoryUnitOfWork, subject: str) -> UUID:
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    unit.application_roles[user_id] = ApplicationRole.OWNER.value
    return user_id


def _seed_connector(
    unit: InMemoryUnitOfWork,
    user_id: UUID,
    *,
    account_id: UUID | None = None,
) -> UUID:
    record = sample_connector_account(
        user_id,
        account_id=account_id,
        provider="gmail",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[record.id] = record
    return record.id


def _user_id_for(unit: InMemoryUnitOfWork, subject: str) -> UUID:
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )
    resolved = IdentityResolver(UnitOfWorkFactory(unit)).find_existing(principal)
    assert resolved is not None
    return resolved


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", _CONTEXTS_URL, {"type": "matter", "title": "X"}),
        ("get", _CONTEXTS_URL, None),
        ("get", f"{_CONTEXTS_URL}/{uuid4()}", None),
        ("patch", f"{_CONTEXTS_URL}/{uuid4()}", {"title": "Y"}),
        ("post", f"{_CONTEXTS_URL}/{uuid4()}/archive", None),
        ("post", f"{_CONTEXTS_URL}/{uuid4()}/restore", None),
        (
            "post",
            f"{_CONTEXTS_URL}/{uuid4()}/communications",
            {
                "connector_account_id": str(uuid4()),
                "provider_message_id": "msg-1",
            },
        ),
        ("get", f"{_CONTEXTS_URL}/{uuid4()}/communications", None),
        ("delete", f"{_CONTEXTS_URL}/{uuid4()}/communications/{uuid4()}", None),
        ("get", f"{_CONTEXTS_URL}/{uuid4()}/timeline", None),
    ],
)
def test_unauthenticated_context_endpoints_return_401(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    method: str,
    path: str,
    json_body: dict | None,
) -> None:
    """Every context endpoint rejects missing bearer tokens."""
    client, _unit, spy, factory = api
    request = getattr(client, method)
    response = request(path, json=json_body) if json_body is not None else request(path)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert spy.calls == []
    assert factory.calls == 0


def test_create_list_get_update_archive_restore_happy_path(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Owner can manage lifecycle without mailbox connection."""
    client, unit, spy, factory = api

    created = _create_context(client, private_key, reference="MAT-9")
    assert created["status"] == "active"
    assert created["archived_at"] is None
    assert created["reference"] == "MAT-9"
    _assert_context_privacy(created)
    assert unit.connector_account_store == {}

    listed = client.get(_CONTEXTS_URL, headers=_analyze_headers(private_key))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]

    got = client.get(
        f"{_CONTEXTS_URL}/{created['id']}",
        headers=_analyze_headers(private_key),
    )
    assert got.status_code == 200
    assert got.json()["title"] == "Matter One"

    patched = client.patch(
        f"{_CONTEXTS_URL}/{created['id']}",
        json={"title": "Matter Renamed", "description": "Updated"},
        headers=_analyze_headers(private_key),
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Matter Renamed"
    assert patched.json()["description"] == "Updated"

    archived = client.post(
        f"{_CONTEXTS_URL}/{created['id']}/archive",
        headers=_analyze_headers(private_key),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["archived_at"] is not None

    active_list = client.get(_CONTEXTS_URL, headers=_analyze_headers(private_key))
    assert active_list.json()["items"] == []

    archived_list = client.get(
        _CONTEXTS_URL,
        params={"status": "archived"},
        headers=_analyze_headers(private_key),
    )
    assert [item["id"] for item in archived_list.json()["items"]] == [created["id"]]

    include_all = client.get(
        _CONTEXTS_URL,
        params={"include_archived": "true"},
        headers=_analyze_headers(private_key),
    )
    assert [item["id"] for item in include_all.json()["items"]] == [created["id"]]

    restored = client.post(
        f"{_CONTEXTS_URL}/{created['id']}/restore",
        headers=_analyze_headers(private_key),
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
    assert restored.json()["archived_at"] is None

    assert spy.calls == []
    assert factory.calls == 0


def test_create_without_mailbox_connection_succeeds(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """BusinessContext CRUD requires application login, not mailbox OAuth."""
    client, unit, _spy, _factory = api
    created = _create_context(client, private_key)
    assert created["id"]
    assert unit.connector_account_store == {}
    assert _user_id_for(unit, _SUBJECT_A) is not None


def test_ownership_injection_fields_are_rejected(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Client cannot supply ownership or lifecycle fields on create/update."""
    client, unit, _spy, _factory = api
    create_response = client.post(
        _CONTEXTS_URL,
        json={
            "type": "matter",
            "title": "Inject",
            "user_id": str(uuid4()),
            "owner_user_id": str(uuid4()),
            "status": "archived",
        },
        headers=_analyze_headers(private_key),
    )
    assert create_response.status_code == 422

    created = _create_context(client, private_key)
    owner_before = _user_id_for(unit, _SUBJECT_A)
    update_response = client.patch(
        f"{_CONTEXTS_URL}/{created['id']}",
        json={"user_id": str(uuid4()), "status": "archived"},
        headers=_analyze_headers(private_key),
    )
    assert update_response.status_code == 422
    stored = unit.business_context_store[UUID(created["id"])]
    assert stored.owner_user_id == owner_before
    assert stored.status.value == "active"


def test_cross_user_and_platform_owner_cannot_access_foreign_context(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Ordinary users and Platform Owners cannot access another user's context."""
    client, unit, _spy, _factory = api
    created = _create_context(client, private_key, subject=_SUBJECT_A)
    _promote_owner(unit, _SUBJECT_OWNER)
    foreign_id = created["id"]

    for subject in (_SUBJECT_B, _SUBJECT_OWNER):
        headers = _analyze_headers(private_key, subject)
        assert (
            client.get(f"{_CONTEXTS_URL}/{foreign_id}", headers=headers).status_code
            == 404
        )
        assert (
            client.patch(
                f"{_CONTEXTS_URL}/{foreign_id}",
                json={"title": "Nope"},
                headers=headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"{_CONTEXTS_URL}/{foreign_id}/archive",
                headers=headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"{_CONTEXTS_URL}/{foreign_id}/restore",
                headers=headers,
            ).status_code
            == 404
        )
        listed = client.get(_CONTEXTS_URL, headers=headers)
        assert listed.status_code == 200
        assert listed.json()["items"] == []


def test_update_archived_context_returns_409(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Archived contexts reject generic field updates."""
    client, _unit, _spy, _factory = api
    created = _create_context(client, private_key)
    assert (
        client.post(
            f"{_CONTEXTS_URL}/{created['id']}/archive",
            headers=_analyze_headers(private_key),
        ).status_code
        == 200
    )
    response = client.patch(
        f"{_CONTEXTS_URL}/{created['id']}",
        json={"title": "Blocked"},
        headers=_analyze_headers(private_key),
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Business context cannot be updated."}


def test_context_crud_requires_analyze_not_read_only(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Context CRUD is gated by communications:analyze, not mailbox connect."""
    client, _unit, _spy, _factory = api
    read_only = _headers(private_key, _SUBJECT_A, COMMUNICATIONS_READ_PERMISSION)
    response = client.post(
        _CONTEXTS_URL,
        json={"type": "matter", "title": "Denied"},
        headers=read_only,
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_association_permission_matrix(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Association requires both communications:read and communications:analyze."""
    client, unit, spy, factory = api
    created = _create_context(client, private_key)
    user_id = _user_id_for(unit, _SUBJECT_A)
    connector_id = _seed_connector(unit, user_id)
    body = {
        "connector_account_id": str(connector_id),
        "provider_message_id": "gmail-msg-1",
    }
    path = f"{_CONTEXTS_URL}/{created['id']}/communications"

    neither = _headers(private_key, _SUBJECT_A, "communications:connect")
    read_only = _headers(private_key, _SUBJECT_A, COMMUNICATIONS_READ_PERMISSION)
    analyze_only = _headers(private_key, _SUBJECT_A, TEST_PERMISSION)
    both = _read_analyze_headers(private_key)

    assert client.post(path, json=body, headers=neither).status_code == 403
    assert client.post(path, json=body, headers=read_only).status_code == 403
    assert client.post(path, json=body, headers=analyze_only).status_code == 403
    ok = client.post(path, json=body, headers=both)
    assert ok.status_code == 201
    assert ok.json()["provider_message_id"] == "gmail-msg-1"
    assert ok.json()["association_source"] == "manual"
    _assert_context_privacy(ok.json())
    assert spy.calls == []
    assert factory.calls == 0


def test_association_ownership_and_platform_owner_boundaries(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Association requires owned context and owned connector; owner role no bypass."""
    client, unit, spy, factory = api
    context_a = _create_context(client, private_key, subject=_SUBJECT_A)
    context_b = _create_context(client, private_key, subject=_SUBJECT_B)
    user_a = _user_id_for(unit, _SUBJECT_A)
    user_b = _user_id_for(unit, _SUBJECT_B)
    connector_a = _seed_connector(unit, user_a)
    connector_b = _seed_connector(unit, user_b)
    _promote_owner(unit, _SUBJECT_OWNER)

    foreign_connector = client.post(
        f"{_CONTEXTS_URL}/{context_a['id']}/communications",
        json={
            "connector_account_id": str(connector_b),
            "provider_message_id": "msg-x",
        },
        headers=_read_analyze_headers(private_key, _SUBJECT_A),
    )
    assert foreign_connector.status_code == 404
    assert foreign_connector.json() == {"detail": "Connector account not found."}

    foreign_context = client.post(
        f"{_CONTEXTS_URL}/{context_b['id']}/communications",
        json={
            "connector_account_id": str(connector_a),
            "provider_message_id": "msg-y",
        },
        headers=_read_analyze_headers(private_key, _SUBJECT_A),
    )
    assert foreign_context.status_code == 404
    assert foreign_context.json() == {"detail": "Business context not found."}

    owner_attempt = client.post(
        f"{_CONTEXTS_URL}/{context_a['id']}/communications",
        json={
            "connector_account_id": str(connector_a),
            "provider_message_id": "msg-z",
        },
        headers=_read_analyze_headers(private_key, _SUBJECT_OWNER),
    )
    assert owner_attempt.status_code == 404

    ok = client.post(
        f"{_CONTEXTS_URL}/{context_a['id']}/communications",
        json={
            "connector_account_id": str(connector_a),
            "provider_message_id": "msg-ok",
        },
        headers=_read_analyze_headers(private_key, _SUBJECT_A),
    )
    assert ok.status_code == 201
    assert spy.calls == []
    assert factory.calls == 0


def test_association_archived_duplicate_analysis_and_removal(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Archived/duplicate/analysis provenance and removal follow 20C rules."""
    client, unit, spy, factory = api
    created = _create_context(client, private_key)
    _create_context(client, private_key, subject=_SUBJECT_B, title="B Context")
    user_id = _user_id_for(unit, _SUBJECT_A)
    user_b = _user_id_for(unit, _SUBJECT_B)
    connector_id = _seed_connector(unit, user_id)
    analysis = sample_analysis_record(
        user_id,
        extra={
            "message_id": "msg-1",
            "connector_account_id": connector_id,
        },
    )
    unit.analyses[analysis.id] = analysis
    foreign_analysis = sample_analysis_record(
        user_b,
        extra={"message_id": "msg-1", "connector_account_id": connector_id},
    )
    unit.analyses[foreign_analysis.id] = foreign_analysis

    path = f"{_CONTEXTS_URL}/{created['id']}/communications"
    headers = _read_analyze_headers(private_key)

    first = client.post(
        path,
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-1",
            "analysis_id": str(analysis.id),
        },
        headers=headers,
    )
    assert first.status_code == 201
    link_id = first.json()["id"]
    assert first.json()["analysis_id"] == str(analysis.id)

    duplicate = client.post(
        path,
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-1",
        },
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "Business context communication link cannot be created."
    }

    mismatched = client.post(
        path,
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-2",
            "analysis_id": str(analysis.id),
        },
        headers=headers,
    )
    assert mismatched.status_code == 404
    assert mismatched.json() == {"detail": "Analysis not found."}

    foreign = client.post(
        path,
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-3",
            "analysis_id": str(foreign_analysis.id),
        },
        headers=headers,
    )
    assert foreign.status_code == 404

    listed = client.get(path, headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [link_id]

    assert (
        client.post(
            f"{_CONTEXTS_URL}/{created['id']}/archive",
            headers=_analyze_headers(private_key),
        ).status_code
        == 200
    )
    archived_associate = client.post(
        path,
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-new",
        },
        headers=headers,
    )
    assert archived_associate.status_code == 409

    removed = client.delete(f"{path}/{link_id}", headers=headers)
    assert removed.status_code == 204
    assert UUID(link_id) not in unit.business_context_communication_link_store
    assert analysis.id in unit.analyses
    assert connector_id in unit.connector_account_store
    assert spy.calls == []
    assert factory.calls == 0


def test_no_hard_delete_context_route(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Physical DELETE of a BusinessContext is not exposed."""
    client, _unit, _spy, _factory = api
    created = _create_context(client, private_key)
    response = client.delete(
        f"{_CONTEXTS_URL}/{created['id']}",
        headers=_analyze_headers(private_key),
    )
    assert response.status_code == 405


def test_timeline_owned_empty_and_deterministic(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Owned timeline returns context_created without provider or AI I/O."""
    client, _unit, spy, factory = api
    created = _create_context(client, private_key, title="Timeline")
    path = f"{_CONTEXTS_URL}/{created['id']}/timeline"

    response = client.get(path, headers=_analyze_headers(private_key))
    assert response.status_code == 200
    payload = response.json()
    _assert_context_privacy(payload)
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["type"] == "context_created"
    assert payload["items"][0]["id"] == f"context_created:{created['id']}"

    again = client.get(path, headers=_analyze_headers(private_key))
    assert again.json()["items"][0]["id"] == payload["items"][0]["id"]
    assert spy.calls == []
    assert factory.calls == 0


def test_timeline_foreign_and_platform_owner_are_404(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Cross-user and Platform Owner timeline access remain 404."""
    client, unit, spy, factory = api
    created = _create_context(client, private_key)
    path = f"{_CONTEXTS_URL}/{created['id']}/timeline"

    foreign = client.get(path, headers=_analyze_headers(private_key, _SUBJECT_B))
    assert foreign.status_code == 404
    assert foreign.json() == {"detail": "Business context not found."}

    _promote_owner(unit, _SUBJECT_OWNER)
    owner = client.get(path, headers=_analyze_headers(private_key, _SUBJECT_OWNER))
    assert owner.status_code == 404
    assert owner.json() == {"detail": "Business context not found."}
    assert spy.calls == []
    assert factory.calls == 0


def test_timeline_projects_association_and_pagination(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Timeline includes association events and paginates deterministically."""
    client, unit, spy, factory = api
    created = _create_context(client, private_key)
    user_id = _user_id_for(unit, _SUBJECT_A)
    connector_id = _seed_connector(unit, user_id)
    headers = _read_analyze_headers(private_key)
    associate = client.post(
        f"{_CONTEXTS_URL}/{created['id']}/communications",
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-timeline",
        },
        headers=headers,
    )
    assert associate.status_code == 201
    link_id = associate.json()["id"]

    page = client.get(
        f"{_CONTEXTS_URL}/{created['id']}/timeline",
        params={"limit": 1, "offset": 0},
        headers=_analyze_headers(private_key),
    )
    assert page.status_code == 200
    assert len(page.json()["items"]) == 1
    assert page.json()["items"][0]["type"] in {
        "communication_associated",
        "context_created",
    }

    full = client.get(
        f"{_CONTEXTS_URL}/{created['id']}/timeline",
        headers=_analyze_headers(private_key),
    )
    types = [item["type"] for item in full.json()["items"]]
    ids = [item["id"] for item in full.json()["items"]]
    assert "context_created" in types
    assert "communication_associated" in types
    assert f"association:{link_id}" in ids
    assert spy.calls == []
    assert factory.calls == 0


def test_timeline_requires_analyze_permission(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Timeline requires communications:analyze (read alone is insufficient)."""
    client, _unit, spy, factory = api
    created = _create_context(client, private_key)
    response = client.get(
        f"{_CONTEXTS_URL}/{created['id']}/timeline",
        headers=_headers(private_key, _SUBJECT_A, COMMUNICATIONS_READ_PERMISSION),
    )
    assert response.status_code == 403
    assert spy.calls == []
    assert factory.calls == 0


def test_context_suggestions_are_advisory_and_do_not_create_links(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Suggestion endpoint returns advisory matches without mailbox I/O or links."""
    client, unit, spy, factory = api
    created = _create_context(
        client,
        private_key,
        title="Alpha Corp Matter",
        reference="MAT-ALPHA",
    )
    user_id = _user_id_for(unit, _SUBJECT_A)
    connector_id = _seed_connector(unit, user_id)
    analysis = sample_analysis_record(
        user_id,
        summary_text="Urgent update about Alpha Corp litigation filing",
        extra={
            "connector_account_id": connector_id,
            "message_id": "msg-suggest-1",
            "action_items": [{"description": "Review Alpha Corp filing"}],
        },
    )
    unit.analyses[analysis.id] = analysis
    link_count_before = len(unit.business_context_communication_link_store)

    response = client.post(
        f"{_CONTEXTS_URL}/suggestions",
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-suggest-1",
            "analysis_id": str(analysis.id),
        },
        headers=_read_analyze_headers(private_key),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "suggestions" in payload
    assert _FORBIDDEN_RESPONSE_KEYS.isdisjoint(_collect_keys(payload))
    assert len(unit.business_context_communication_link_store) == link_count_before
    assert spy.calls == []
    assert factory.calls == 0
    if payload["suggestions"]:
        assert payload["suggestions"][0]["business_context_id"] == created["id"]
        assert payload["suggestions"][0]["match_strength"] in {
            "high",
            "medium",
            "low",
        }


def test_context_suggestions_permission_and_ownership_matrix(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """Suggestions require read+analyze and reject foreign analysis/connectors."""
    client, unit, spy, factory = api
    _create_context(client, private_key, title="Alpha")
    user_a = _user_id_for(unit, _SUBJECT_A)
    connector_id = _seed_connector(unit, user_a)
    analysis = sample_analysis_record(
        user_a,
        summary_text="Alpha summary",
        extra={
            "connector_account_id": connector_id,
            "message_id": "msg-suggest-2",
        },
    )
    unit.analyses[analysis.id] = analysis
    body = {
        "connector_account_id": str(connector_id),
        "provider_message_id": "msg-suggest-2",
        "analysis_id": str(analysis.id),
    }

    analyze_only = client.post(
        f"{_CONTEXTS_URL}/suggestions",
        json=body,
        headers=_analyze_headers(private_key),
    )
    assert analyze_only.status_code == 403

    read_only = client.post(
        f"{_CONTEXTS_URL}/suggestions",
        json=body,
        headers=_headers(private_key, _SUBJECT_A, COMMUNICATIONS_READ_PERMISSION),
    )
    assert read_only.status_code == 403

    _create_context(client, private_key, subject=_SUBJECT_B, title="B Matter")
    user_b = _user_id_for(unit, _SUBJECT_B)
    foreign_analysis = sample_analysis_record(
        user_b,
        extra={
            "connector_account_id": connector_id,
            "message_id": "msg-suggest-2",
        },
    )
    unit.analyses[foreign_analysis.id] = foreign_analysis
    foreign = client.post(
        f"{_CONTEXTS_URL}/suggestions",
        json={
            **body,
            "analysis_id": str(foreign_analysis.id),
        },
        headers=_read_analyze_headers(private_key),
    )
    assert foreign.status_code == 404

    owner = client.post(
        f"{_CONTEXTS_URL}/suggestions",
        json=body,
        headers=_read_analyze_headers(private_key, _SUBJECT_OWNER),
    )
    assert owner.status_code == 404
    assert spy.calls == []
    assert factory.calls == 0


def test_context_suggestions_ai_failure_does_not_block_manual_associate(
    api: tuple[
        TestClient,
        InMemoryUnitOfWork,
        _SpyConnector,
        StaticCommunicationConnectorFactory,
    ],
    private_key,
) -> None:
    """AI suggestion failure leaves the existing associate path usable."""
    client, unit, spy, factory = api
    created = _create_context(client, private_key, title="Manual Matter")
    user_id = _user_id_for(unit, _SUBJECT_A)
    connector_id = _seed_connector(unit, user_id)
    analysis = sample_analysis_record(
        user_id,
        summary_text="Manual path remains available",
        extra={
            "connector_account_id": connector_id,
            "message_id": "msg-suggest-3",
        },
    )
    unit.analyses[analysis.id] = analysis

    application = client.app
    application.dependency_overrides[get_ai_provider] = lambda: MockAIProvider(
        suggestion_error=RuntimeError("provider down")
    )
    failed = client.post(
        f"{_CONTEXTS_URL}/suggestions",
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-suggest-3",
            "analysis_id": str(analysis.id),
        },
        headers=_read_analyze_headers(private_key),
    )
    assert failed.status_code == 500

    associated = client.post(
        f"{_CONTEXTS_URL}/{created['id']}/communications",
        json={
            "connector_account_id": str(connector_id),
            "provider_message_id": "msg-suggest-3",
            "analysis_id": str(analysis.id),
        },
        headers=_read_analyze_headers(private_key),
    )
    assert associated.status_code == 201, associated.text
    assert spy.calls == []
    assert factory.calls == 0
