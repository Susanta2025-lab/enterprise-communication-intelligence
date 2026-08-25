"""HTTP tests for configured mailbox OAuth callback frontend return."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_connector_account_oauth_service,
    get_connector_account_service,
    get_gmail_mailbox_oauth_callback_service,
    get_gmail_mailbox_oauth_service,
    get_microsoft_mailbox_oauth_callback_service,
    get_microsoft_mailbox_oauth_service,
    get_token_validator,
)
from app.application.services.connector_account_oauth import ConnectorAccountOAuthService
from app.application.services.connector_accounts import ConnectorAccountService
from app.application.services.gmail_mailbox_oauth import GmailMailboxOAuthService
from app.application.services.identity import IdentityResolver
from app.application.services.microsoft_mailbox_oauth import MicrosoftMailboxOAuthService
from app.core.config import get_settings
from app.core.exceptions import MailboxOAuthAuthorizationFailedError
from app.core.security import COMMUNICATIONS_CONNECT_PERMISSION
from app.domain.enums import CommunicationCapability, ConnectorAccountStatus
from app.domain.interfaces.communication_credential_store import CommunicationCredentialRecord
from app.infrastructure.credentials.locators import create_communication_credential
from app.infrastructure.credentials.memory import InMemoryCommunicationCredentialStore
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
from tests.unit.application.test_gmail_mailbox_oauth import (
    FakeMailboxOAuthClient as GmailFakeClient,
)
from tests.unit.application.test_gmail_mailbox_oauth import _authorization_result as gmail_result
from tests.unit.application.test_microsoft_mailbox_oauth import (
    FakeMailboxOAuthClient as MicrosoftFakeClient,
)
from tests.unit.application.test_microsoft_mailbox_oauth import (
    _authorization_result as microsoft_result,
)

_GMAIL_AUTHORIZE = "/api/v1/connector-accounts/gmail/authorize"
_GMAIL_CALLBACK = "/api/v1/oauth/callbacks/gmail"
_GRAPH_AUTHORIZE = "/api/v1/connector-accounts/microsoft_graph/authorize"
_GRAPH_CALLBACK = "/api/v1/oauth/callbacks/microsoft_graph"
_REAUTHORIZE = "/api/v1/connector-accounts/{connector_account_id}/reauthorize"
_RETURN_URL = "http://localhost:5173"
_SENSITIVE = (
    "code",
    "state",
    "access_token",
    "refresh_token",
    "id_token",
    "credential_ref",
    "external_account_id",
    "error_description",
    "pkce",
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
    get_settings.cache_clear()


def _enable_oidc_env(monkeypatch: pytest.MonkeyPatch, *, return_url: str | None) -> None:
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("OIDC_AUDIENCE", TEST_AUDIENCE)
    monkeypatch.setenv("OIDC_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setenv("OIDC_REQUIRED_PERMISSION", TEST_PERMISSION)
    monkeypatch.setenv("FRONTEND_OAUTH_RETURN_URL", return_url or "")


def _connect_header(private_key) -> dict[str, str]:
    token = encode_test_token(
        private_key,
        extra_claims={"scp": f"{TEST_PERMISSION} {COMMUNICATIONS_CONNECT_PERMISSION}"},
    )
    return bearer_header(token)


def _assert_safe_location(location: str, *, oauth: str, provider: str) -> None:
    parsed = urlparse(location)
    assert parsed.scheme == "http"
    assert parsed.netloc == "localhost:5173"
    query = parse_qs(parsed.query)
    assert query == {"oauth": [oauth], "provider": [provider]}
    lowered = location.lower()
    for marker in _SENSITIVE:
        assert marker not in lowered
    assert "connector_account_id" not in lowered
    assert "evil.example" not in lowered


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


def _gmail_bundle(client: GmailFakeClient | None = None):
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    store = InMemoryCommunicationCredentialStore()
    oauth_client = client or GmailFakeClient()

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="gmail",
            secret_material=secret_material,
        )

    identity = IdentityResolver(factory)
    gmail = GmailMailboxOAuthService(
        identity,
        factory,
        oauth_client,
        store,
        create_stored,
    )
    accounts = ConnectorAccountService(identity, factory, credential_store=store)
    return gmail, oauth_client, unit, store, accounts


def _graph_bundle(client: MicrosoftFakeClient | None = None):
    unit = InMemoryUnitOfWork()
    factory = UnitOfWorkFactory(unit)
    store = InMemoryCommunicationCredentialStore()
    oauth_client = client or MicrosoftFakeClient()

    def create_stored(secret_material: bytes) -> CommunicationCredentialRecord:
        return create_communication_credential(
            store,
            provider="microsoft_graph",
            secret_material=secret_material,
        )

    identity = IdentityResolver(factory)
    graph = MicrosoftMailboxOAuthService(
        identity,
        factory,
        oauth_client,
        store,
        create_stored,
    )
    accounts = ConnectorAccountService(identity, factory, credential_store=store)
    return graph, oauth_client, unit, store, accounts


def _gmail_app(monkeypatch, private_key, *, return_url: str | None, client=None):
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch, return_url=return_url)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    gmail, fake, unit, store, accounts = _gmail_bundle(client)
    oauth = ConnectorAccountOAuthService(
        accounts,
        lambda: gmail,
        lambda: (_ for _ in ()).throw(AssertionError("microsoft must not be used")),
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_gmail_mailbox_oauth_service] = lambda: gmail
    application.dependency_overrides[get_gmail_mailbox_oauth_callback_service] = lambda: gmail
    application.dependency_overrides[get_connector_account_service] = lambda: accounts
    application.dependency_overrides[get_connector_account_oauth_service] = lambda: oauth
    return application, fake, unit, store


def _graph_app(monkeypatch, private_key, *, return_url: str | None, client=None):
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch, return_url=return_url)
    get_settings.cache_clear()
    validator = make_test_validator(private_key)
    graph, fake, unit, store, accounts = _graph_bundle(client)
    oauth = ConnectorAccountOAuthService(
        accounts,
        lambda: (_ for _ in ()).throw(AssertionError("gmail must not be used")),
        lambda: graph,
    )
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_microsoft_mailbox_oauth_service] = lambda: graph
    application.dependency_overrides[get_microsoft_mailbox_oauth_callback_service] = lambda: graph
    application.dependency_overrides[get_connector_account_service] = lambda: accounts
    application.dependency_overrides[get_connector_account_oauth_service] = lambda: oauth
    return application, fake, unit, store


@pytest.fixture
def gmail_json_client(monkeypatch: pytest.MonkeyPatch, private_key) -> Iterator[tuple]:
    application, fake, unit, store = _gmail_app(monkeypatch, private_key, return_url=None)
    with TestClient(application) as test_client:
        yield test_client, fake, unit, store, private_key


@pytest.fixture
def gmail_redirect_client(monkeypatch: pytest.MonkeyPatch, private_key) -> Iterator[tuple]:
    application, fake, unit, store = _gmail_app(
        monkeypatch, private_key, return_url=_RETURN_URL
    )
    with TestClient(application) as test_client:
        yield test_client, fake, unit, store, private_key


@pytest.fixture
def graph_json_client(monkeypatch: pytest.MonkeyPatch, private_key) -> Iterator[tuple]:
    application, fake, unit, store = _graph_app(monkeypatch, private_key, return_url=None)
    with TestClient(application) as test_client:
        yield test_client, fake, unit, store, private_key


@pytest.fixture
def graph_redirect_client(monkeypatch: pytest.MonkeyPatch, private_key) -> Iterator[tuple]:
    application, fake, unit, store = _graph_app(
        monkeypatch, private_key, return_url=_RETURN_URL
    )
    with TestClient(application) as test_client:
        yield test_client, fake, unit, store, private_key


def test_gmail_unconfigured_callback_remains_json(gmail_json_client) -> None:
    client, fake, _unit, _store, private_key = gmail_json_client
    started = client.post(_GMAIL_AUTHORIZE, headers=_connect_header(private_key))
    assert started.status_code == 200
    response = client.get(
        _GMAIL_CALLBACK,
        params={"state": fake.last_state, "code": "AUTH_CODE_SENTINEL_RETURN_JSON"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gmail"
    assert payload["status"] == ConnectorAccountStatus.ACTIVE.value
    assert "credential_ref" not in payload
    assert fake.exchange_calls == 1


def test_graph_unconfigured_callback_remains_json(graph_json_client) -> None:
    client, fake, _unit, _store, private_key = graph_json_client
    started = client.post(_GRAPH_AUTHORIZE, headers=_connect_header(private_key))
    assert started.status_code == 200
    response = client.get(
        _GRAPH_CALLBACK,
        params={"state": fake.last_state, "code": "AUTH_CODE_SENTINEL_RETURN_JSON_MS"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "microsoft_graph"
    assert payload["status"] == ConnectorAccountStatus.ACTIVE.value
    assert "credential_ref" not in payload
    assert fake.exchange_calls == 1


@pytest.mark.parametrize(
    ("fixture_name", "authorize", "callback", "provider", "code"),
    [
        (
            "gmail_redirect_client",
            _GMAIL_AUTHORIZE,
            _GMAIL_CALLBACK,
            "gmail",
            "AUTH_CODE_SENTINEL_RETURN_OK",
        ),
        (
            "graph_redirect_client",
            _GRAPH_AUTHORIZE,
            _GRAPH_CALLBACK,
            "microsoft_graph",
            "AUTH_CODE_SENTINEL_RETURN_OK_MS",
        ),
    ],
)
def test_configured_success_redirects_without_secrets(
    fixture_name,
    authorize,
    callback,
    provider,
    code,
    request,
) -> None:
    client, fake, unit, _store, private_key = request.getfixturevalue(fixture_name)
    started = client.post(authorize, headers=_connect_header(private_key))
    assert started.status_code == 200
    response = client.get(
        callback,
        params={
            "state": fake.last_state,
            "code": code,
            "return_to": "https://evil.example/phish",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="success", provider=provider)
    assert fake.last_state not in location
    assert code not in location
    assert fake.exchange_calls == 1
    stored = next(iter(unit.connector_account_store.values()))
    assert stored.status is ConnectorAccountStatus.ACTIVE
    assert str(stored.id) not in location
    assert stored.external_account_id not in location
    assert stored.credential_ref not in location


@pytest.mark.parametrize(
    ("fixture_name", "authorize", "callback", "provider"),
    [
        ("gmail_redirect_client", _GMAIL_AUTHORIZE, _GMAIL_CALLBACK, "gmail"),
        ("graph_redirect_client", _GRAPH_AUTHORIZE, _GRAPH_CALLBACK, "microsoft_graph"),
    ],
)
def test_configured_denied_redirects_after_session_consume(
    fixture_name,
    authorize,
    callback,
    provider,
    request,
) -> None:
    client, fake, _unit, _store, private_key = request.getfixturevalue(fixture_name)
    client.post(authorize, headers=_connect_header(private_key))
    response = client.get(
        callback,
        params={
            "state": fake.last_state,
            "error": "access_denied",
            "error_description": "user declined evil_scope",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="denied", provider=provider)
    assert fake.exchange_calls == 0
    assert "access_denied" not in location
    assert "evil_scope" not in location
    assert "error_description" not in location


@pytest.mark.parametrize(
    ("fixture_name", "callback", "provider"),
    [
        ("gmail_redirect_client", _GMAIL_CALLBACK, "gmail"),
        ("graph_redirect_client", _GRAPH_CALLBACK, "microsoft_graph"),
    ],
)
def test_configured_expired_session_redirects_without_exchange(
    fixture_name,
    callback,
    provider,
    request,
) -> None:
    client, fake, _unit, _store, _key = request.getfixturevalue(fixture_name)
    response = client.get(
        callback,
        params={"state": "missing-session", "code": "AUTH_CODE_EXPIRED_SESSION"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="expired", provider=provider)
    assert fake.exchange_calls == 0
    assert "missing-session" not in location
    assert "AUTH_CODE_EXPIRED_SESSION" not in location


def test_gmail_configured_exchange_failure_is_sanitized_redirect(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    application, fake, _unit, _store = _gmail_app(
        monkeypatch,
        private_key,
        return_url=_RETURN_URL,
        client=GmailFakeClient(exchange_error=MailboxOAuthAuthorizationFailedError()),
    )
    with TestClient(application) as client:
        started = client.post(_GMAIL_AUTHORIZE, headers=_connect_header(private_key))
        assert started.status_code == 200
        response = client.get(
            _GMAIL_CALLBACK,
            params={"state": fake.last_state, "code": "AUTH_CODE_PROVIDER_FAIL"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="failed", provider="gmail")
    assert fake.exchange_calls == 1
    assert "AUTH_CODE_PROVIDER_FAIL" not in location
    assert fake.last_state not in location


def test_graph_configured_exchange_failure_is_sanitized_redirect(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    application, fake, _unit, _store = _graph_app(
        monkeypatch,
        private_key,
        return_url=_RETURN_URL,
        client=MicrosoftFakeClient(exchange_error=MailboxOAuthAuthorizationFailedError()),
    )
    with TestClient(application) as client:
        started = client.post(_GRAPH_AUTHORIZE, headers=_connect_header(private_key))
        assert started.status_code == 200
        response = client.get(
            _GRAPH_CALLBACK,
            params={"state": fake.last_state, "code": "AUTH_CODE_PROVIDER_FAIL_MS"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="failed", provider="microsoft_graph")
    assert fake.exchange_calls == 1
    assert "AUTH_CODE_PROVIDER_FAIL_MS" not in location
    assert fake.last_state not in location


def test_gmail_identity_mismatch_redirects_and_preserves_bound_account(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    application, fake, unit, _store = _gmail_app(
        monkeypatch,
        private_key,
        return_url=_RETURN_URL,
        client=GmailFakeClient(gmail_result(subject="google-oidc-sub-other")),
    )
    user_id = uuid4()
    unit.identities[(TEST_ISSUER, TEST_SUBJECT)] = user_id
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="google-oidc-sub-bound",
        credential_ref="oauth-bound-locator",
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        started = client.post(
            _REAUTHORIZE.format(connector_account_id=account.id),
            headers=_connect_header(private_key),
        )
        assert started.status_code == 200
        response = client.get(
            _GMAIL_CALLBACK,
            params={"state": fake.last_state, "code": "AUTH_CODE_IDENTITY_MISMATCH"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="identity_mismatch", provider="gmail")
    assert fake.exchange_calls == 1
    assert "google-oidc-sub-other" not in location
    assert "google-oidc-sub-bound" not in location
    bound = unit.connector_account_store[account.id]
    assert bound.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert bound.external_account_id == "google-oidc-sub-bound"
    assert bound.credential_ref == "oauth-bound-locator"


def test_graph_identity_mismatch_redirects_and_preserves_bound_account(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    application, fake, unit, store = _graph_app(
        monkeypatch,
        private_key,
        return_url=_RETURN_URL,
        client=MicrosoftFakeClient(
            microsoft_result(
                external_account_id="other-tid:other-oid",
                object_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            )
        ),
    )
    user_id = uuid4()
    unit.identities[(TEST_ISSUER, TEST_SUBJECT)] = user_id
    account = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id="bound-tid:bound-oid",
        credential_ref="oauth-bound-locator-ms",
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        started = client.post(
            _REAUTHORIZE.format(connector_account_id=account.id),
            headers=_connect_header(private_key),
        )
        assert started.status_code == 200
        response = client.get(
            _GRAPH_CALLBACK,
            params={"state": fake.last_state, "code": "AUTH_CODE_IDENTITY_MISMATCH_MS"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    location = response.headers["location"]
    _assert_safe_location(location, oauth="identity_mismatch", provider="microsoft_graph")
    assert fake.exchange_calls == 1
    bound = unit.connector_account_store[account.id]
    assert bound.status is ConnectorAccountStatus.REAUTH_REQUIRED
    assert bound.external_account_id == "bound-tid:bound-oid"
    assert bound.credential_ref == "oauth-bound-locator-ms"
    assert store is not None


def test_gmail_unconfigured_identity_mismatch_remains_failed_json(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> None:
    application, fake, unit, _store = _gmail_app(
        monkeypatch,
        private_key,
        return_url=None,
        client=GmailFakeClient(gmail_result(subject="google-oidc-sub-other")),
    )
    user_id = uuid4()
    unit.identities[(TEST_ISSUER, TEST_SUBJECT)] = user_id
    account = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="google-oidc-sub-bound",
        credential_ref="oauth-bound-locator-json",
        status=ConnectorAccountStatus.REAUTH_REQUIRED,
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    unit.connector_account_store[account.id] = account
    with TestClient(application) as client:
        started = client.post(
            _REAUTHORIZE.format(connector_account_id=account.id),
            headers=_connect_header(private_key),
        )
        assert started.status_code == 200
        response = client.get(
            _GMAIL_CALLBACK,
            params={"state": fake.last_state, "code": "AUTH_CODE_IDENTITY_JSON"},
            follow_redirects=False,
        )
    assert response.status_code == 400
    assert response.json() == {"detail": "Mailbox authorization failed."}
    assert "google-oidc-sub-other" not in response.text
    assert unit.connector_account_store[account.id].status is ConnectorAccountStatus.REAUTH_REQUIRED
