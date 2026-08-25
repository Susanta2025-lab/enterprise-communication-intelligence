"""HTTP tests for Microsoft mailbox OAuth start and callback."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_microsoft_mailbox_oauth_callback_service,
    get_microsoft_mailbox_oauth_service,
    get_token_validator,
)
from app.application.services.identity import IdentityResolver
from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService
from app.core.config import get_settings
from app.core.security import COMMUNICATIONS_CONNECT_PERMISSION
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.communication_credential_store import CommunicationCredentialRecord
from app.infrastructure.credentials.locators import create_communication_credential
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
from app.main import create_app
from tests.support.in_memory_persistence import InMemoryUnitOfWork, UnitOfWorkFactory
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
from tests.unit.application.test_microsoft_mailbox_oauth import FakeMailboxOAuthClient

_AUTHORIZE_URL = "/api/v1/connector-accounts/microsoft_graph/authorize"
_CALLBACK_URL = "/api/v1/oauth/callbacks/microsoft_graph"
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


def _build_service(
    client: FakeMailboxOAuthClient | None = None,
) -> tuple[MicrosoftMailboxOAuthService, FakeMailboxOAuthClient, InMemoryUnitOfWork]:
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    oauth_client = client or FakeMailboxOAuthClient()
    store = InMemoryCommunicationCredentialStore()

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="microsoft_graph",
            secret_material=secret_material,
        )

    service = MicrosoftMailboxOAuthService(
        IdentityResolver(factory),
        factory,
        oauth_client,
        store,
        create_stored,
    )
    return service, oauth_client, unit


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def oauth_app(monkeypatch: pytest.MonkeyPatch, private_key):
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    service, client, unit = _build_service()
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_microsoft_mailbox_oauth_service] = lambda: service
    application.dependency_overrides[get_microsoft_mailbox_oauth_callback_service] = lambda: service
    return application, service, client, unit, private_key


@pytest.fixture
def oauth_client(oauth_app) -> Iterator[TestClient]:
    application, _service, _fake, _unit, _key = oauth_app
    with TestClient(application) as test_client:
        yield test_client


def _connect_header(private_key) -> dict[str, str]:
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_CONNECT_PERMISSION}"},
    )
    return bearer_header(token)


def test_authorize_requires_bearer(oauth_client: TestClient) -> None:
    response = oauth_client.post(_AUTHORIZE_URL)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_authorize_requires_connect_permission(
    oauth_app,
    oauth_client: TestClient,
) -> None:
    _application, _service, _fake, _unit, private_key = oauth_app
    token = encode_test_token(private_key, extra_claims={"scp": TEST_PERMISSION})
    response = oauth_client.post(_AUTHORIZE_URL, headers=bearer_header(token))
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_authorize_returns_url_without_secrets(
    oauth_app,
    oauth_client: TestClient,
) -> None:
    _application, _service, fake, unit, private_key = oauth_app
    response = oauth_client.post(_AUTHORIZE_URL, headers=_connect_header(private_key))
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"authorization_url", "expires_at"}
    assert fake.last_state is not None
    assert fake.last_state in payload["authorization_url"]
    assert fake.last_challenge in payload["authorization_url"]
    assert "credential_ref" not in payload
    assert "state" not in payload
    assert "code_challenge" not in payload
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.pkce_verifier not in response.text


def test_callback_does_not_require_eci_bearer(
    oauth_app,
    oauth_client: TestClient,
) -> None:
    _application, _service, fake, _unit, _key = oauth_app
    response = oauth_client.get(_CALLBACK_URL, params={"state": "missing", "code": "x"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox authorization session is invalid."}
    assert fake.exchange_calls == 0
    assert "Authorization" not in {header.title() for header in oauth_client.headers}


def test_callback_success_without_bearer(
    oauth_app,
    oauth_client: TestClient,
) -> None:
    _application, _service, fake, _unit, private_key = oauth_app
    started = oauth_client.post(_AUTHORIZE_URL, headers=_connect_header(private_key))
    assert started.status_code == 200
    response = oauth_client.get(
        _CALLBACK_URL,
        params={"state": fake.last_state, "code": "AUTH_CODE_SENTINEL_HTTP_MS"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "microsoft_graph"
    assert payload["status"] == ConnectorAccountStatus.ACTIVE.value
    assert payload["granted_capabilities"] == [
        CommunicationCapability.MAIL_READ.value,
        CommunicationCapability.MAIL_SEND.value,
    ]
    assert "credential_ref" not in payload
    assert "refresh_token" not in payload
    assert "access_token" not in response.text
    assert fake.exchange_calls == 1


def test_callback_denial_does_not_exchange(
    oauth_app,
    oauth_client: TestClient,
) -> None:
    _application, _service, fake, _unit, private_key = oauth_app
    oauth_client.post(_AUTHORIZE_URL, headers=_connect_header(private_key))
    response = oauth_client.get(
        _CALLBACK_URL,
        params={"state": fake.last_state, "error": "access_denied"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox authorization was denied."}
    assert fake.exchange_calls == 0
    assert "access_denied" not in response.text.lower()
    assert "error_description" not in response.text


def test_callback_without_oauth_config_is_not_401(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    """Unauthenticated callback must not require the ECI bearer token."""
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    # Blank env values override a local `.env` so this test stays offline.
    for name in (
        "MICROSOFT_OAUTH_CLIENT_ID",
        "MICROSOFT_OAUTH_CLIENT_SECRET",
        "MICROSOFT_OAUTH_REDIRECT_URI",
        "MICROSOFT_OAUTH_TENANT",
        "DATABASE_URL",
    ):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    with TestClient(application) as test_client:
        response = test_client.get(_CALLBACK_URL, params={"state": "x", "code": "y"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Microsoft mailbox authorization is unavailable."}
