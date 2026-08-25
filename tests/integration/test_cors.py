"""Integration tests for browser CORS configuration."""

from collections.abc import Iterator

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from app.core.config import get_settings
from app.main import create_app

_FRONTEND_ORIGIN = "http://localhost:5173"
_OTHER_ORIGIN = "http://localhost:4173"
_HEALTH_URL = "/api/v1/health"
_ANALYSES_URL = "/api/v1/analyses"
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
    "CORS_ALLOWED_ORIGINS",
)


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()


def _cors_middleware(application) -> Middleware | None:
    for middleware in application.user_middleware:
        if middleware.cls is CORSMiddleware:
            return middleware
    return None


@pytest.fixture
def cors_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with the local frontend origin allowlisted."""
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", _FRONTEND_ORIGIN)
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def backend_only_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with no CORS origins configured."""
    _clear_settings_env(monkeypatch)
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_allowed_origin_preflight_permits_authorization_header(
    cors_client: TestClient,
) -> None:
    response = cors_client.options(
        _ANALYSES_URL,
        headers={
            "Origin": _FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type,x-request-id",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _FRONTEND_ORIGIN
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow_headers
    assert "content-type" in allow_headers
    assert "x-request-id" in allow_headers
    assert response.headers.get("access-control-allow-credentials") in {None, "false"}
    assert "*" not in response.headers.get("access-control-allow-origin", "")


def test_allowed_origin_receives_cors_headers_on_get(
    cors_client: TestClient,
) -> None:
    response = cors_client.get(_HEALTH_URL, headers={"Origin": _FRONTEND_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == _FRONTEND_ORIGIN
    assert response.headers.get("access-control-allow-origin") != "*"
    assert response.headers.get("access-control-allow-credentials") in {None, "false"}


def test_unconfigured_origin_does_not_receive_permissive_cors_headers(
    cors_client: TestClient,
) -> None:
    response = cors_client.get(_HEALTH_URL, headers={"Origin": _OTHER_ORIGIN})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != _OTHER_ORIGIN
    assert response.headers.get("access-control-allow-origin") != "*"


def test_unconfigured_origin_preflight_is_not_permitted(
    cors_client: TestClient,
) -> None:
    response = cors_client.options(
        _ANALYSES_URL,
        headers={
            "Origin": _OTHER_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.headers.get("access-control-allow-origin") != _OTHER_ORIGIN
    assert response.headers.get("access-control-allow-origin") != "*"


def test_empty_allowlist_does_not_enable_cors_middleware(
    backend_only_client: TestClient,
) -> None:
    middleware = _cors_middleware(backend_only_client.app)
    assert middleware is None
    response = backend_only_client.get(
        _HEALTH_URL,
        headers={"Origin": _FRONTEND_ORIGIN},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_middleware_never_enables_credentials_or_wildcard(
    cors_client: TestClient,
) -> None:
    middleware = _cors_middleware(cors_client.app)
    assert middleware is not None
    kwargs = middleware.kwargs
    assert kwargs["allow_credentials"] is False
    assert "*" not in kwargs["allow_origins"]
    assert kwargs["allow_origins"] == [_FRONTEND_ORIGIN]
    assert "Authorization" in kwargs["allow_headers"]
    assert "Content-Type" in kwargs["allow_headers"]
    assert "X-Request-ID" in kwargs["allow_headers"]


def test_existing_health_and_protected_route_behavior_unchanged(
    cors_client: TestClient,
) -> None:
    health = cors_client.get(_HEALTH_URL)
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    analyses = cors_client.get(f"{_ANALYSES_URL}?limit=1")
    assert analyses.status_code == 401
    assert "access_token" not in analyses.text
