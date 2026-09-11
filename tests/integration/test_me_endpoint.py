"""Integration tests for server-authoritative GET /api/v1/me."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_token_validator, get_unit_of_work_factory
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
from app.core.exceptions import PersistenceError
from app.core.security import (
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    AuthenticatedPrincipal,
)
from app.domain.enums import ApplicationRole, CommunicationCapability
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

_ME_URL = "/api/v1/me"
_ADMIN_PING = "/api/v1/admin/ping"
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
_ALL_COMMUNICATIONS = (
    TEST_PERMISSION,
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_CONNECT_PERMISSION,
    COMMUNICATIONS_WORKFLOW_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
)
_FORBIDDEN_ME_FIELDS = frozenset(
    {
        "iss",
        "issuer",
        "sub",
        "subject",
        "email",
        "preferred_username",
        "access_token",
        "id_token",
        "mailbox",
        "user_id",
        "roles",
        "scp",
        "permissions",
    }
)


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


def _token(
    private_key,
    *,
    subject: str = TEST_SUBJECT,
    permissions: tuple[str, ...] = (TEST_PERMISSION,),
    extra_claims: dict | None = None,
) -> str:
    claims: dict = {"scp": " ".join(permissions)}
    if extra_claims:
        claims.update(extra_claims)
    return encode_test_token(private_key, subject=subject, extra_claims=claims)


def _seed_user(
    unit: InMemoryUnitOfWork,
    *,
    subject: str = TEST_SUBJECT,
    role: str = ApplicationRole.USER.value,
) -> None:
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=subject,
        permissions=frozenset({TEST_PERMISSION}),
    )
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    unit.application_roles[user_id] = role


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def me_api(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[tuple[TestClient, InMemoryUnitOfWork]]:
    _clear_settings_env(monkeypatch)
    _enable_oidc_env(monkeypatch)
    get_settings.cache_clear()
    unit = InMemoryUnitOfWork()
    validator = make_test_validator(private_key)
    application = create_app()
    application.dependency_overrides[get_token_validator] = lambda: validator
    application.dependency_overrides[get_unit_of_work_factory] = lambda: UnitOfWorkFactory(
        unit
    )
    with TestClient(application) as test_client:
        yield test_client, unit


def test_me_authenticated_user_returns_user_role(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    response = client.get(
        _ME_URL,
        headers=bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS)),
    )
    assert response.status_code == 200
    assert response.json() == {"application_role": "user", "is_owner": False}


def test_me_persisted_owner_returns_owner_role(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.OWNER.value)
    response = client.get(
        _ME_URL,
        headers=bearer_header(_token(private_key, permissions=(TEST_PERMISSION,))),
    )
    assert response.status_code == 200
    assert response.json() == {"application_role": "owner", "is_owner": True}


def test_me_unauthenticated_returns_401(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
) -> None:
    client, _unit = me_api
    response = client.get(_ME_URL)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers.get("www-authenticate") == "Bearer"


def test_me_unknown_identity_does_not_create_user(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    create_calls_before = unit.identity_repository.create_calls
    response = client.get(
        _ME_URL,
        headers=bearer_header(_token(private_key, permissions=(TEST_PERMISSION,))),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Application identity was not found."}
    assert unit.identity_repository.create_calls == create_calls_before
    assert unit.identities == {}
    assert unit.application_roles == {}


def test_jwt_roles_and_scopes_cannot_change_me_db_role(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    response = client.get(
        _ME_URL,
        headers=bearer_header(
            _token(
                private_key,
                permissions=_ALL_COMMUNICATIONS,
                extra_claims={"roles": ["owner", "Admin"]},
            )
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"application_role": "user", "is_owner": False}


def test_mailbox_identity_cannot_influence_me(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    user_id = next(iter(unit.application_roles))
    unit.connector_account_store[uuid4()] = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="mailbox-owner@example.invalid",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    response = client.get(
        _ME_URL,
        headers=bearer_header(
            _token(
                private_key,
                permissions=_ALL_COMMUNICATIONS,
                extra_claims={
                    "email": "mailbox-owner@example.invalid",
                    "preferred_username": "mailbox-owner@example.invalid",
                },
            )
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"application_role": "user", "is_owner": False}


def test_graph_mailbox_identity_cannot_influence_me(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    user_id = next(iter(unit.application_roles))
    unit.connector_account_store[uuid4()] = sample_connector_account(
        user_id,
        provider="microsoft_graph",
        external_account_id="graph-owner@example.invalid",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    response = client.get(
        _ME_URL,
        headers=bearer_header(
            _token(
                private_key,
                permissions=_ALL_COMMUNICATIONS,
                extra_claims={
                    "email": "graph-owner@example.invalid",
                    "preferred_username": "graph-owner@example.invalid",
                },
            )
        ),
    )
    assert response.status_code == 200
    assert response.json() == {"application_role": "user", "is_owner": False}


def test_corrupt_application_role_fails_closed_on_me(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role="admin")
    response = client.get(
        _ME_URL,
        headers=bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS)),
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Application identity is currently unavailable."}


def test_me_persistence_failure_returns_503(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)

    def _boom(_issuer: str, _subject: str):
        raise PersistenceError("simulated failure")

    monkeypatch.setattr(
        unit.identity_repository,
        "get_user_id_by_external_identity",
        _boom,
    )
    response = client.get(
        _ME_URL,
        headers=bearer_header(_token(private_key, permissions=(TEST_PERMISSION,))),
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Persistence is currently unavailable."}


def test_me_response_exposes_no_sensitive_identity_fields(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.OWNER.value)
    response = client.get(
        _ME_URL,
        headers=bearer_header(_token(private_key, permissions=(TEST_PERMISSION,))),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"application_role", "is_owner"}
    assert not _FORBIDDEN_ME_FIELDS.intersection(body.keys())


def test_client_role_headers_cannot_change_me_or_admin_ping(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    """Frontend-style role claims must not affect /me or require_owner."""
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    headers = bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS))
    headers["X-Application-Role"] = "owner"
    headers["X-ECI-Owner"] = "true"
    me_response = client.get(_ME_URL, headers=headers)
    assert me_response.status_code == 200
    assert me_response.json() == {"application_role": "user", "is_owner": False}
    ping = client.get(_ADMIN_PING, headers=headers)
    assert ping.status_code == 403


def test_require_owner_unchanged_when_me_reports_user(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    headers = bearer_header(
        _token(
            private_key,
            permissions=_ALL_COMMUNICATIONS,
            extra_claims={"roles": ["owner"]},
        )
    )
    assert client.get(_ME_URL, headers=headers).json()["is_owner"] is False
    assert client.get(_ADMIN_PING, headers=headers).status_code == 403


def test_me_does_not_expose_role_write_methods(
    me_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = me_api
    _seed_user(unit, role=ApplicationRole.OWNER.value)
    headers = bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS))
    for method in ("post", "put", "patch", "delete"):
        response = client.request(method, _ME_URL, headers=headers, json={"role": "owner"})
        assert response.status_code == 405
