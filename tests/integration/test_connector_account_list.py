"""HTTP tests for owned connector-account listing."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_token_validator, get_unit_of_work_factory
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.security import (
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
)
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.infrastructure.oauth import runtime as oauth_runtime
from app.main import create_app
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

_LIST_URL = "/api/v1/connector-accounts"
_FORBIDDEN_FIELDS = (
    "credential_ref",
    "external_account_id",
    "locator",
    "refresh_token",
    "access_token",
    "id_token",
    "oauth_token",
    "pkce_verifier",
    "user_id",
)
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
    "FRONTEND_OAUTH_RETURN_URL",
    "GMAIL_OAUTH_CLIENT_ID",
    "GMAIL_OAUTH_CLIENT_SECRET",
    "GMAIL_OAUTH_REDIRECT_URI",
    "MICROSOFT_OAUTH_CLIENT_ID",
    "MICROSOFT_OAUTH_CLIENT_SECRET",
    "MICROSOFT_OAUTH_REDIRECT_URI",
    "MICROSOFT_OAUTH_TENANT",
    "CREDENTIAL_STORE_BACKEND",
    "AZURE_KEY_VAULT_URL",
    "AWS_SECRETS_MANAGER_REGION",
    "AWS_SECRETS_MANAGER_NAMESPACE",
)


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", "")
    get_settings.cache_clear()


def _enable_oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("OIDC_REQUIRED_PERMISSION", TEST_PERMISSION)


def _read_header(private_key, *, subject: str = TEST_SUBJECT) -> dict[str, str]:
    token = encode_test_token(
        private_key,
        subject=subject,
        extra_claims={"scp": COMMUNICATIONS_READ_PERMISSION},
    )
    return bearer_header(token)


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


def _store_unavailable(*_args, **_kwargs):
    raise ServiceUnavailableError("Gmail mailbox authorization is unavailable.")


@pytest.fixture
def list_app(monkeypatch: pytest.MonkeyPatch, private_key):
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    monkeypatch.setattr(oauth_runtime, "require_shared_oauth_store", _store_unavailable)
    validator = make_test_validator(private_key)
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: factory
    return application, unit, private_key


@pytest.fixture
def list_client(list_app) -> Iterator[TestClient]:
    application, _unit, _key = list_app
    with TestClient(application) as test_client:
        yield test_client


def _seed_account(
    unit: InMemoryUnitOfWork,
    *,
    owner_subject: str = TEST_SUBJECT,
    provider: str = "gmail",
    status: ConnectorAccountStatus = ConnectorAccountStatus.ACTIVE,
    external_account_id: str = "google-oidc-sub-list-001",
    credential_ref: str | None = "oauth-list-locator-01",
    granted_capabilities: tuple[CommunicationCapability, ...] | None = (
        CommunicationCapability.MAIL_READ,
        CommunicationCapability.MAIL_SEND,
    ),
):
    user_id = unit.identities.get((TEST_ISSUER, owner_subject))
    if user_id is None:
        user_id = uuid4()
        unit.identities[(TEST_ISSUER, owner_subject)] = user_id
    account = sample_connector_account(
        user_id,
        provider=provider,
        external_account_id=external_account_id,
        credential_ref=credential_ref,
        status=status,
        granted_capabilities=granted_capabilities,
    )
    unit.connector_account_store[account.id] = account
    return account


def test_list_requires_bearer(list_client: TestClient) -> None:
    response = list_client.get(_LIST_URL)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_list_requires_communications_read(list_app, list_client: TestClient) -> None:
    _application, unit, private_key = list_app
    _seed_account(unit)
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_CONNECT_PERMISSION}"},
    )
    response = list_client.get(_LIST_URL, headers=bearer_header(token))
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_list_empty_when_principal_has_no_identity(
    list_client: TestClient,
    private_key,
) -> None:
    response = list_client.get(_LIST_URL, headers=_read_header(private_key))
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"items": [], "limit": 20, "offset": 0}


def test_list_returns_only_owned_accounts(list_app, list_client: TestClient, private_key) -> None:
    _application, unit, _key = list_app
    owned = _seed_account(unit, owner_subject=TEST_SUBJECT)
    other = _seed_account(
        unit,
        owner_subject="other-mailbox-owner",
        provider="microsoft_graph",
        external_account_id="tid:oid-other-001",
        credential_ref="oauth-list-locator-other",
    )
    response = list_client.get(_LIST_URL, headers=_read_header(private_key))
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert [item["id"] for item in payload["items"]] == [str(owned.id)]
    serialized = response.text
    assert str(other.id) not in serialized
    assert other.external_account_id not in serialized
    assert other.credential_ref not in serialized


def test_list_includes_lifecycle_states_and_capabilities(
    list_app,
    list_client: TestClient,
    private_key,
) -> None:
    _application, unit, _key = list_app
    user_id = uuid4()
    unit.identities[(TEST_ISSUER, TEST_SUBJECT)] = user_id
    active = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="google-oidc-sub-active",
        credential_ref="oauth-active-locator",
        status=ConnectorAccountStatus.ACTIVE,
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    reauth = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id="tid:oid-reauth",
        credential_ref="oauth-reauth-locator",
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    disconnected = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="google-oidc-sub-disconnected",
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
        granted_capabilities=None,
    )
    unit.connector_account_store[active.id] = active
    unit.connector_account_store[reauth.id] = reauth
    unit.connector_account_store[disconnected.id] = disconnected

    response = list_client.get(_LIST_URL, headers=_read_header(private_key))
    assert response.status_code == 200
    payload = response.json()
    by_id = {item["id"]: item for item in payload["items"]}
    assert set(by_id) == {str(active.id), str(reauth.id), str(disconnected.id)}
    assert by_id[str(active.id)]["status"] == "active"
    assert by_id[str(active.id)]["granted_capabilities"] == ["mail.read", "mail.send"]
    assert by_id[str(reauth.id)]["status"] == "reauth_required"
    assert by_id[str(reauth.id)]["granted_capabilities"] == ["mail.read"]
    assert by_id[str(disconnected.id)]["status"] == "disconnected"
    assert by_id[str(disconnected.id)]["granted_capabilities"] is None
    for item in payload["items"]:
        assert set(item) == {
            "id",
            "provider",
            "status",
            "granted_capabilities",
            "created_at",
            "updated_at",
        }
    serialized = response.text.lower()
    for field in _FORBIDDEN_FIELDS:
        assert field not in serialized
    assert "oauth-active-locator" not in response.text
    assert "google-oidc-sub-active" not in response.text
    assert "tid:oid-reauth" not in response.text


def test_list_pagination_bounds(list_app, list_client: TestClient, private_key) -> None:
    _application, unit, _key = list_app
    first = _seed_account(unit, external_account_id="google-oidc-sub-page-1")
    second = _seed_account(
        unit,
        provider="microsoft_graph",
        external_account_id="tid:oid-page-2",
        credential_ref="oauth-list-locator-02",
    )
    headers = _read_header(private_key)
    page = list_client.get(f"{_LIST_URL}?limit=1&offset=0", headers=headers)
    rest = list_client.get(f"{_LIST_URL}?limit=1&offset=1", headers=headers)
    assert page.status_code == 200
    assert rest.status_code == 200
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 0
    assert rest.json()["limit"] == 1
    assert rest.json()["offset"] == 1
    page_ids = {item["id"] for item in page.json()["items"]}
    rest_ids = {item["id"] for item in rest.json()["items"]}
    assert page_ids.isdisjoint(rest_ids)
    assert page_ids | rest_ids == {str(first.id), str(second.id)}
    assert list_client.get(f"{_LIST_URL}?limit=0", headers=headers).status_code == 422
    assert list_client.get(f"{_LIST_URL}?limit=101", headers=headers).status_code == 422
    assert list_client.get(f"{_LIST_URL}?offset=-1", headers=headers).status_code == 422


def test_list_does_not_require_communications_connect(
    list_app,
    list_client: TestClient,
    private_key,
) -> None:
    """Metadata listing is authorized by communications:read alone."""
    _application, unit, _key = list_app
    owned = _seed_account(unit)
    token = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_READ_PERMISSION},
    )
    response = list_client.get(f"{_LIST_URL}?limit=20&offset=0", headers=bearer_header(token))
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    assert [item["id"] for item in payload["items"]] == [str(owned.id)]
    assert payload["items"][0]["provider"] == "gmail"
    serialized = response.text.lower()
    for field in _FORBIDDEN_FIELDS:
        assert field not in serialized


def test_list_succeeds_when_mailbox_oauth_store_is_unavailable(
    list_app,
    list_client: TestClient,
    private_key,
) -> None:
    """Former production wiring required the shared OAuth store and returned 503."""
    _application, unit, _key = list_app
    owned = _seed_account(unit, provider="microsoft_graph", external_account_id="tid:oid-aws-001")
    token = encode_test_token(
        private_key,
        extra_claims={
            "scp": " ".join(
                (
                    COMMUNICATIONS_READ_PERMISSION,
                    TEST_PERMISSION,
                    COMMUNICATIONS_CONNECT_PERMISSION,
                    COMMUNICATIONS_WORKFLOW_PERMISSION,
                    COMMUNICATIONS_SEND_PERMISSION,
                )
            )
        },
    )
    response = list_client.get(f"{_LIST_URL}?limit=20&offset=0", headers=bearer_header(token))
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [str(owned.id)]
    assert "oauth-list-locator-01" not in response.text
    with pytest.raises(ServiceUnavailableError):
        oauth_runtime.require_shared_oauth_store(get_settings())
