"""Integration tests for first-owner bootstrap and require_owner acceptance."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_token_validator, get_unit_of_work_factory
from app.application.services.identity import IdentityResolver
from app.application.services.owner_bootstrap import (
    FirstOwnerBootstrapResult,
    FirstOwnerBootstrapService,
)
from app.cli.promote_owner import main as promote_owner_main
from app.core.config import get_settings
from app.core.security import (
    COMMUNICATIONS_READ_PERMISSION,
    COMMUNICATIONS_SEND_PERMISSION,
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


@pytest.fixture
def private_key():
    return generate_test_rsa_private_key()


@pytest.fixture
def bootstrap_api(
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


def test_bootstrap_then_require_owner_accepts(
    bootstrap_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = bootstrap_api
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    denied = client.get(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key)),
    )
    assert denied.status_code == 403

    result = FirstOwnerBootstrapService(UnitOfWorkFactory(unit)).promote_first_owner(user_id)
    assert result is FirstOwnerBootstrapResult.PROMOTED

    allowed = client.get(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key)),
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"status": "ok"}


def test_mailbox_identity_cannot_select_or_promote(
    bootstrap_api: tuple[TestClient, InMemoryUnitOfWork],
) -> None:
    _client, unit = bootstrap_api
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    account_id = uuid4()
    unit.connector_account_store[account_id] = sample_connector_account(
        user_id,
        account_id=account_id,
        provider="gmail",
        external_account_id="mailbox-owner@example.invalid",
        granted_capabilities=(CommunicationCapability.MAIL_READ,),
    )
    assert unit.application_roles[user_id] == ApplicationRole.USER.value
    # No bootstrap API accepts mailbox ids; role remains user.
    assert account_id not in unit.application_roles


def test_jwt_roles_cannot_promote(
    bootstrap_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = bootstrap_api
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )
    IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    response = client.get(
        _ADMIN_PING,
        headers=bearer_header(
            _token(
                private_key,
                permissions=(
                    TEST_PERMISSION,
                    COMMUNICATIONS_READ_PERMISSION,
                    COMMUNICATIONS_SEND_PERMISSION,
                ),
                extra_claims={"roles": ["owner"]},
            )
        ),
    )
    assert response.status_code == 403
    user_id = next(iter(unit.application_roles))
    assert unit.application_roles[user_id] == ApplicationRole.USER.value


def test_no_http_endpoint_modifies_application_role(
    bootstrap_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = bootstrap_api
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    headers = bearer_header(_token(private_key))
    for method, path in (
        ("post", "/api/v1/admin/users/promote"),
        ("patch", f"/api/v1/users/{user_id}/role"),
        ("put", "/api/v1/users/me/role"),
        ("post", "/api/v1/admin/bootstrap"),
        ("post", "/api/v1/admin/ping"),
    ):
        response = client.request(
            method,
            path,
            headers=headers,
            json={"application_role": "owner", "user_id": str(user_id)},
        )
        assert response.status_code in {404, 405}
    assert unit.application_roles[user_id] == ApplicationRole.USER.value


def test_ordinary_user_cannot_self_promote_via_api(
    bootstrap_api: tuple[TestClient, InMemoryUnitOfWork],
    private_key,
) -> None:
    client, unit = bootstrap_api
    principal = AuthenticatedPrincipal(
        issuer=TEST_ISSUER,
        subject=TEST_SUBJECT,
        permissions=frozenset({TEST_PERMISSION}),
    )
    user_id = IdentityResolver(UnitOfWorkFactory(unit)).resolve_or_create(principal)
    response = client.post(
        _ADMIN_PING,
        headers=bearer_header(_token(private_key)),
        json={"application_role": "owner"},
    )
    assert response.status_code == 405
    assert unit.application_roles[user_id] == ApplicationRole.USER.value


def test_cli_rejects_non_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    assert promote_owner_main(["--user-id", "not-a-uuid"]) == 2


def test_cli_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("AUTH_MODE", "disabled")
    get_settings.cache_clear()
    assert promote_owner_main(["--user-id", str(uuid4())]) == 2
