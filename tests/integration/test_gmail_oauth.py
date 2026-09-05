"""HTTP tests for Gmail mailbox OAuth start and callback."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_gmail_mailbox_oauth_callback_service,
    get_gmail_mailbox_oauth_service,
    get_token_validator,
)
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.exceptions import MailboxOAuthAuthorizationFailedError
from app.core.security import COMMUNICATIONS_CONNECT_PERMISSION
from app.domain.enums import (
    CommunicationCapability,
    ConnectorAccountStatus,
    MailboxAuthorizationPurpose,
)
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
from tests.unit.application.test_gmail_mailbox_oauth import _GOOGLE_SUB, FakeMailboxOAuthClient

_AUTHORIZE_URL = "/api/v1/connector-accounts/gmail/authorize"
_AUTHORIZE_ANOTHER_URL = "/api/v1/connector-accounts/gmail/authorize/another"
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
) -> tuple[GmailMailboxOAuthService, FakeMailboxOAuthClient, InMemoryUnitOfWork]:
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    oauth_client = client or FakeMailboxOAuthClient()
    store = InMemoryCommunicationCredentialStore()

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="gmail",
            secret_material=secret_material,
        )

    service = GmailMailboxOAuthService(
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
    application.dependency_overrides[get_gmail_mailbox_oauth_service] = lambda: service
    application.dependency_overrides[get_gmail_mailbox_oauth_callback_service] = lambda: service
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
    assert fake.last_account_selection is False


def test_authorize_another_returns_url_without_binding_existing_account(
    oauth_app,
    oauth_client: TestClient,
) -> None:
    _application, _service, fake, unit, private_key = oauth_app
    response = oauth_client.post(_AUTHORIZE_ANOTHER_URL, headers=_connect_header(private_key))
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"authorization_url", "expires_at"}
    stored = next(iter(unit.mailbox_authorization_session_store.values()))
    assert stored.purpose is MailboxAuthorizationPurpose.CONNECT_ANOTHER
    assert stored.connector_account_id is None
    assert fake.last_account_selection is True
    assert fake.last_state not in ("state",)
    assert "state" not in payload
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
        params={"state": fake.last_state, "code": "AUTH_CODE_SENTINEL_HTTP"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gmail"
    assert payload["status"] == ConnectorAccountStatus.ACTIVE.value
    assert payload["granted_capabilities"] == [
        CommunicationCapability.MAIL_READ.value,
        CommunicationCapability.MAIL_SEND.value,
    ]
    assert "credential_ref" not in payload
    assert "external_account_id" not in payload
    assert _GOOGLE_SUB not in response.text
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


def test_callback_exchange_failure_is_sanitized_400(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    service, fake, _unit = _build_service(
        client=FakeMailboxOAuthClient(
            exchange_error=MailboxOAuthAuthorizationFailedError(),
        )
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_gmail_mailbox_oauth_service] = lambda: service
    application.dependency_overrides[get_gmail_mailbox_oauth_callback_service] = lambda: service
    with TestClient(application) as test_client:
        started = test_client.post(_AUTHORIZE_URL, headers=_connect_header(private_key))
        assert started.status_code == 200
        response = test_client.get(
            _CALLBACK_URL,
            params={"state": fake.last_state, "code": "AUTH_CODE_SENTINEL_HTTP_FAIL"},
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox authorization failed."}
    assert fake.exchange_calls == 1
    assert "AUTH_CODE_SENTINEL_HTTP_FAIL" not in response.text
    assert "oauth_error" not in response.text
    assert "refresh_token" not in response.text
    assert "id_token" not in response.text
    assert "error_description" not in response.text


def test_callback_id_token_verify_failure_is_sanitized_400(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
    log_events: list[dict],
) -> None:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    email = "callback-mailbox@example.com"
    subject = "google-sub-callback-verify-001"
    id_token = "PRIV_CALLBACK_ID_TOKEN_SENTINEL_HHH"
    code = "AUTH_CODE_SENTINEL_HTTP_VERIFY_FAIL"

    def fetch(_code: str, _verifier: str) -> dict[str, str]:
        return {
            "refresh_token": "PRIV_CALLBACK_REFRESH_SENTINEL_III",
            "id_token": id_token,
            "access_token": "PRIV_CALLBACK_ACCESS_SENTINEL_JJJ",
            "scope": (
                "openid https://www.googleapis.com/auth/gmail.readonly "
                "https://www.googleapis.com/auth/gmail.send"
            ),
        }

    def verify(token: str) -> dict[str, str]:
        raise ValueError(f"audience mismatch {token} sub={subject} email={email}")

    from app.infrastructure.oauth.google import GoogleMailboxOAuthClient

    oauth_client = GoogleMailboxOAuthClient(
        client_id="test-client-id.apps.googleusercontent.com",
        client_secret="PRIV_CALLBACK_CLIENT_SECRET_KKK",
        redirect_uri="https://eci.example.invalid/api/v1/oauth/callbacks/gmail",
        token_fetcher=fetch,
        id_token_verifier=verify,
    )
    service, _fake, unit = _build_service(client=oauth_client)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_gmail_mailbox_oauth_service] = lambda: service
    application.dependency_overrides[get_gmail_mailbox_oauth_callback_service] = (
        lambda: service
    )
    with TestClient(application) as test_client:
        started = test_client.post(_AUTHORIZE_URL, headers=_connect_header(private_key))
        assert started.status_code == 200
        authorization_url = started.json()["authorization_url"]
        state = parse_qs(urlparse(authorization_url).query)["state"][0]
        stored = next(iter(unit.mailbox_authorization_session_store.values()))
        pkce_verifier = stored.pkce_verifier
        assert pkce_verifier is not None
        response = test_client.get(
            _CALLBACK_URL,
            params={"state": state, "code": code},
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox authorization failed."}
    text = response.text
    assert id_token not in text
    assert email not in text
    assert subject not in text
    assert code not in text
    assert "audience mismatch" not in text
    verify_failed = [
        event
        for event in log_events
        if event.get("event") == "gmail_oauth_id_token_verify_failed"
    ]
    assert len(verify_failed) == 1
    assert verify_failed[0]["provider"] == "gmail"
    assert verify_failed[0]["operation"] == "verify_id_token"
    assert verify_failed[0]["verify_error_class"] == "ValueError"
    assert "verify_error_reason" not in verify_failed[0]
    assert verify_failed[0]["subject_present"] is False
    blob = repr(log_events) + text
    assert id_token not in blob
    assert email not in blob
    assert subject not in blob
    assert "PRIV_CALLBACK_REFRESH_SENTINEL_III" not in blob
    assert "PRIV_CALLBACK_ACCESS_SENTINEL_JJJ" not in blob
    assert "PRIV_CALLBACK_CLIENT_SECRET_KKK" not in blob
    assert state not in blob
    assert pkce_verifier not in blob


def test_callback_without_oauth_config_is_not_401(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    """Unauthenticated callback must not require the ECI bearer token."""
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    with TestClient(application) as test_client:
        response = test_client.get(_CALLBACK_URL, params={"state": "x", "code": "y"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Gmail mailbox authorization is unavailable."}
