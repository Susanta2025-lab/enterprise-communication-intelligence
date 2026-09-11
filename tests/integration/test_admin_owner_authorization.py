"""Integration tests for server-side platform owner authorization."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_token_validator, get_unit_of_work_factory
from app.application.services.identity import IdentityResolver
from app.core.config import get_settings
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

_ADMIN_PING = "/api/v1/admin/ping"
_ANALYZE_URL = "/api/v1/communications/analyze"
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
def owner_api(
    monkeypatch: pytest.MonkeyPatch,
    private_key,
) -> Iterator[tuple[TestClient, InMemoryUnitOfWork]]:
    """OIDC client with in-memory persistence for owner authorization tests."""
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


def test_admin_ping_without_token_returns_401(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
) -> None:
    client, _unit = owner_api
    response = client.get(_ADMIN_PING)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
    assert response.headers.get("www-authenticate") == "Bearer"


def test_admin_ping_ordinary_user_returns_403(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS)),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_admin_ping_persisted_owner_returns_200(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.OWNER.value)
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key, permissions=(TEST_PERMISSION,))),
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jwt_roles_owner_claim_with_db_user_still_403(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(
            _token(
                private_key,
                permissions=_ALL_COMMUNICATIONS,
                extra_claims={"roles": ["owner"]},
            )
        ),
    )
    assert response.status_code == 403


def test_client_claiming_owner_via_header_body_query_still_403(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    headers = bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS))
    headers["X-Application-Role"] = "owner"
    headers["X-ECI-Owner"] = "true"
    response = client.get(
        f"{_ADMIN_PING}?application_role=owner&role=owner",
        headers=headers,
    )
    assert response.status_code == 403
    post_like = client.request(
        "GET",
        _ADMIN_PING,
        headers=headers,
        content=b'{"application_role":"owner","role":"owner"}',
    )
    assert post_like.status_code == 403


def test_communications_scopes_alone_cannot_satisfy_owner(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS)),
    )
    assert response.status_code == 403


def test_mailbox_connector_identity_cannot_influence_owner(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    user_id = next(iter(unit.application_roles))
    unit.connector_account_store[uuid4()] = sample_connector_account(
        user_id,
        provider="gmail",
        external_account_id="mailbox-owner@example.invalid",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    response = client.get(
        _ADMIN_PING,
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
    assert response.status_code == 403
    assert unit.application_roles[user_id] == ApplicationRole.USER.value


def test_identity_resolution_uses_verified_iss_sub(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, subject=TEST_SUBJECT, role=ApplicationRole.OWNER.value)
    other_subject = "different-test-subject"
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(
            _token(private_key, subject=other_subject, permissions=(TEST_PERMISSION,))
        ),
    )
    assert response.status_code == 403
    assert (TEST_ISSUER, other_subject) not in unit.identities


def test_role_lookup_is_scoped_to_resolved_eci_user(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, subject="user-a", role=ApplicationRole.USER.value)
    _seed_user(unit, subject="user-b", role=ApplicationRole.OWNER.value)
    denied = client.get(
        _ADMIN_PING,
        headers=bearer_header(
            _token(private_key, subject="user-a", permissions=(TEST_PERMISSION,))
        ),
    )
    allowed = client.get(
        _ADMIN_PING,
        headers=bearer_header(
            _token(private_key, subject="user-b", permissions=(TEST_PERMISSION,))
        ),
    )
    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_ordinary_analyze_endpoint_still_works_for_non_owner(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.USER.value)
    payload = {
        "message": {
            "body": "Sharing the notes from today's standup for visibility.",
            "message_id": "msg-001",
            "metadata": {
                "source_type": "email",
                "sender": "alice@example.com",
                "recipients": ["bob@example.com"],
                "subject": "Standup notes",
            },
        },
        "include_draft_reply": False,
        "include_action_items": False,
    }
    response = client.post(
        _ANALYZE_URL,
        json=payload,
        headers=bearer_header(_token(private_key, permissions=(TEST_PERMISSION,))),
    )
    assert response.status_code == 200
    body = response.json()
    assert "analysis" in body
    assert "summary" in body["analysis"]


def test_cross_user_isolation_unchanged_for_owner_probe(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, subject="owner-subject", role=ApplicationRole.OWNER.value)
    _seed_user(unit, subject="other-subject", role=ApplicationRole.USER.value)
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(
            _token(private_key, subject="other-subject", permissions=_ALL_COMMUNICATIONS)
        ),
    )
    assert response.status_code == 403


def test_corrupt_application_role_fails_closed(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role="admin")
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS)),
    )
    assert response.status_code == 403


def test_no_owner_promotion_endpoints_exist(
    owner_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = owner_api
    _seed_user(unit, role=ApplicationRole.OWNER.value)
    headers = bearer_header(_token(private_key, permissions=_ALL_COMMUNICATIONS))
    for method, path in (
        ("post", "/api/v1/admin/users/promote"),
        ("patch", "/api/v1/admin/users/role"),
        ("put", "/api/v1/users/me/role"),
        ("post", "/api/v1/admin/bootstrap"),
    ):
        response = client.request(method, path, headers=headers, json={"role": "owner"})
        assert response.status_code == 404
