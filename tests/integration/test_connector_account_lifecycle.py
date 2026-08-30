"""HTTP tests for connector-account disconnect and reauthorize."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_connector_account_oauth_service,
    get_connector_account_service,
    get_gmail_mailbox_oauth_callback_service,
    get_token_validator,
)
from app.application.services.connector_account_oauth import ConnectorAccountOAuthService
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.security import COMMUNICATIONS_CONNECT_PERMISSION, COMMUNICATIONS_READ_PERMISSION
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.communication_credential_store import (
    CommunicationCredentialRecord,
    NewCommunicationCredential,
)
from app.infrastructure.credentials.locators import create_communication_credential
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.infrastructure.oauth.google import GMAIL_READONLY_SCOPE, serialize_google_mailbox_secret
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
from tests.unit.application.test_gmail_mailbox_oauth import FakeMailboxOAuthClient

_DISCONNECT_URL = "/api/v1/connector-accounts/{connector_account_id}/disconnect"
_REAUTHORIZE_URL = "/api/v1/connector-accounts/{connector_account_id}/reauthorize"
_CALLBACK_URL = "/api/v1/oauth/callbacks/gmail"
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
    "GMAIL_OAUTH_CLIENT_ID",
    "GMAIL_OAUTH_CLIENT_SECRET",
    "GMAIL_OAUTH_REDIRECT_URI",
    "MICROSOFT_OAUTH_CLIENT_ID",
    "MICROSOFT_OAUTH_CLIENT_SECRET",
    "MICROSOFT_OAUTH_REDIRECT_URI",
    "MICROSOFT_OAUTH_TENANT",
    "FRONTEND_OAUTH_RETURN_URL",
)
_LOCATOR = "oauth-http-disconnect-01"
_GOOGLE_SUB = "google-oidc-sub-http-001"
_REFRESH = "REFRESH_TOKEN_SENTINEL_HTTP_DISC"


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


def _connect_header(private_key) -> dict[str, str]:
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_CONNECT_PERMISSION}"},
    )
    return bearer_header(token)


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def lifecycle_app(monkeypatch: pytest.MonkeyPatch, private_key):
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    store = InMemoryCommunicationCredentialStore()
    oauth_client = FakeMailboxOAuthClient()
    identity = IdentityResolver(factory)
    accounts = ConnectorAccountService(identity, factory, credential_store=store)

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="gmail",
            secret_material=secret_material,
        )

    gmail = GmailMailboxOAuthService(
        identity,
        factory,
        oauth_client,
        store,
        create_stored,
    )
    oauth = ConnectorAccountOAuthService(
        accounts,
        lambda: gmail,
        lambda: (_ for _ in ()).throw(AssertionError("microsoft must not be used")),
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_connector_account_service] = lambda: accounts
    application.dependency_overrides[get_connector_account_oauth_service] = lambda: oauth
    application.dependency_overrides[get_gmail_mailbox_oauth_callback_service] = lambda: gmail
    return application, accounts, gmail, oauth_client, unit, store, private_key


@pytest.fixture
def lifecycle_client(lifecycle_app) -> Iterator[TestClient]:
    application, *_rest = lifecycle_app
    with TestClient(application) as test_client:
        yield test_client


def _seed_gmail_account(
    unit: InMemoryUnitOfWork,
    store: InMemoryCommunicationCredentialStore,
    *,
    status: ConnectorAccountStatus,
    locator: str | None = _LOCATOR,
    owner_subject: str = TEST_SUBJECT,
) -> object:
    user_id = uuid4()
    unit.identities[(TEST_ISSUER, owner_subject)] = user_id
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id=_GOOGLE_SUB,
        credential_ref=locator,
        status=status,
        granted_capabilities=(
            CommunicationCapability.MAIL_READ,
            CommunicationCapability.MAIL_SEND,
        ),
    )
    unit.connector_account_store[account.id] = account
    if locator:
        store.create(
            NewCommunicationCredential(
                locator,
                "gmail",
                serialize_google_mailbox_secret(
                    refresh_token=_REFRESH,
                    scopes=(GMAIL_READONLY_SCOPE,),
                    subject=_GOOGLE_SUB,
                ),
            )
        )
    return account


def test_disconnect_requires_bearer(lifecycle_client: TestClient) -> None:
    from uuid import uuid4

    response = lifecycle_client.post(_DISCONNECT_URL.format(connector_account_id=uuid4()))
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_disconnect_requires_connect_permission(
    lifecycle_app, lifecycle_client: TestClient
) -> None:
    _application, _accounts, _gmail, _fake, unit, store, private_key = lifecycle_app
    account = _seed_gmail_account(unit, store, status=ConnectorAccountStatus.ACTIVE)
    token = encode_test_token(private_key, extra_claims={"scp": TEST_PERMISSION})
    response = lifecycle_client.post(
        _DISCONNECT_URL.format(connector_account_id=account.id),
        headers=bearer_header(token),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE


def test_disconnect_owned_account_clears_secret_and_omits_locator(
    lifecycle_app,
    lifecycle_client: TestClient,
    private_key,
) -> None:
    _application, _accounts, _gmail, _fake, unit, store, _key = lifecycle_app
    account = _seed_gmail_account(unit, store, status=ConnectorAccountStatus.ACTIVE)
    response = lifecycle_client.post(
        _DISCONNECT_URL.format(connector_account_id=account.id),
        headers=_connect_header(private_key),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == ConnectorAccountStatus.DISCONNECTED.value
    assert payload["granted_capabilities"] is None
    assert payload["id"] == str(account.id)
    assert "credential_ref" not in payload
    assert "external_account_id" not in payload
    assert _GOOGLE_SUB not in response.text
    assert _LOCATOR not in response.text
    assert _REFRESH not in response.text
    assert store.get(_LOCATOR) is None
    stored = unit.connector_account_store[account.id]
    assert stored.credential_ref is None
    assert stored.status is ConnectorAccountStatus.DISCONNECTED


def test_unknown_and_cross_user_disconnect_are_404(
    lifecycle_app,
    lifecycle_client: TestClient,
    private_key,
) -> None:
    _application, _accounts, _gmail, _fake, unit, store, _key = lifecycle_app
    account = _seed_gmail_account(
        unit,
        store,
        status=ConnectorAccountStatus.ACTIVE,
        owner_subject="mailbox-owner",
    )
    unit.identities[(TEST_ISSUER, TEST_SUBJECT)] = uuid4()
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_CONNECT_PERMISSION}"},
    )
    missing = lifecycle_client.post(
        _DISCONNECT_URL.format(connector_account_id=uuid4()),
        headers=bearer_header(token),
    )
    other = lifecycle_client.post(
        _DISCONNECT_URL.format(connector_account_id=account.id),
        headers=bearer_header(token),
    )
    assert missing.status_code == 404
    assert other.status_code == 404
    assert missing.json() == other.json() == {"detail": "Connector account not found."}
    assert str(account.id) not in missing.text


def test_reauthorize_active_conflicts_and_disconnected_starts(
    lifecycle_app,
    lifecycle_client: TestClient,
    private_key,
) -> None:
    _application, _accounts, _gmail, fake, unit, store, _key = lifecycle_app
    active = _seed_gmail_account(unit, store, status=ConnectorAccountStatus.ACTIVE)
    owner_id = active.user_id
    disconnected = sample_connector_account(
        owner_id,
        provider="gmail",
        external_account_id="google-oidc-sub-http-002",
        credential_ref=None,
        status=ConnectorAccountStatus.DISCONNECTED,
    )
    unit.connector_account_store[disconnected.id] = disconnected
    headers = _connect_header(private_key)
    conflict = lifecycle_client.post(
        _REAUTHORIZE_URL.format(connector_account_id=active.id),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "Connector account cannot be updated."}
    started = lifecycle_client.post(
        _REAUTHORIZE_URL.format(connector_account_id=disconnected.id),
        headers=headers,
    )
    assert started.status_code == 200
    payload = started.json()
    assert set(payload) == {"authorization_url", "expires_at"}
    assert fake.last_state is not None
    assert fake.last_state in payload["authorization_url"]
    assert "credential_ref" not in payload
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.connector_account_id == disconnected.id
    assert stored.pkce_verifier not in started.text


def test_disconnect_rejects_read_without_connect(
    lifecycle_app, lifecycle_client: TestClient
) -> None:
    """communications:read does not authorize disconnect."""
    _application, _accounts, _gmail, _fake, unit, store, private_key = lifecycle_app
    account = _seed_gmail_account(unit, store, status=ConnectorAccountStatus.ACTIVE)
    token = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_READ_PERMISSION},
    )
    response = lifecycle_client.post(
        _DISCONNECT_URL.format(connector_account_id=account.id),
        headers=bearer_header(token),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.ACTIVE
    assert store.get(_LOCATOR) is not None


def test_reauthorize_requires_connect_permission(
    lifecycle_app, lifecycle_client: TestClient
) -> None:
    """Reauthorization remains communications:connect protected."""
    _application, _accounts, _gmail, fake, unit, store, private_key = lifecycle_app
    account = _seed_gmail_account(unit, store, status=ConnectorAccountStatus.DISCONNECTED)
    analyze_only = encode_test_token(private_key, extra_claims={"scp": TEST_PERMISSION})
    read_only = encode_test_token(
        private_key,
        extra_claims={"scp": COMMUNICATIONS_READ_PERMISSION},
    )
    for token in (analyze_only, read_only):
        response = lifecycle_client.post(
            _REAUTHORIZE_URL.format(connector_account_id=account.id),
            headers=bearer_header(token),
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Not authorized"}
    assert fake.last_state is None
    assert unit.mailbox_authorization_session_store == {}
