"""Integration tests for health and readiness endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_database_readiness_probe
from app.core.config import get_settings
from app.main import create_app

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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Build a TestClient with default settings."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client


def test_root_health_endpoint(client: TestClient) -> None:
    """GET /health should return a lightweight liveness payload."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_versioned_health_endpoint(client: TestClient) -> None:
    """GET /api/v1/health should return application metadata."""
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "Enterprise Communication Intelligence Platform",
        "version": "0.1.0",
        "environment": "development",
    }


def test_readiness_endpoint(client: TestClient) -> None:
    """GET /api/v1/readiness should confirm configuration is loaded."""
    response = client.get("/api/v1/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_when_persistence_disabled_remains_ready(client: TestClient) -> None:
    """Omitting DATABASE_URL must not make development unreadiness."""
    response = client.get("/api/v1/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


@pytest.fixture
def client_with_ready_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with a successful database probe override."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[get_database_readiness_probe] = lambda: (lambda: True)
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def client_with_unavailable_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient with a failing database probe override."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    application = create_app()
    application.dependency_overrides[get_database_readiness_probe] = lambda: (lambda: False)
    with TestClient(application) as test_client:
        yield test_client


def test_readiness_when_database_ready(client_with_ready_database: TestClient) -> None:
    """A successful database probe keeps readiness 200."""
    response = client_with_ready_database.get("/api/v1/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_when_database_unavailable(
    client_with_unavailable_database: TestClient,
) -> None:
    """An unavailable database fails closed with a generic 503."""
    response = client_with_unavailable_database.get("/api/v1/readiness")
    assert response.status_code == 503
    payload = response.json()
    assert payload == {"detail": "Persistence is currently unavailable."}
    text = response.text.lower()
    assert "sqlalchemy" not in text
    assert "localhost" not in text
    assert "password" not in text
    assert "postgresql" not in text


def test_health_does_not_query_database_when_probe_fails(
    client_with_unavailable_database: TestClient,
) -> None:
    """GET /health and GET /api/v1/health stay process-only."""
    root = client_with_unavailable_database.get("/health")
    versioned = client_with_unavailable_database.get("/api/v1/health")
    assert root.status_code == 200
    assert root.json() == {"status": "healthy"}
    assert versioned.status_code == 200
    assert versioned.json()["status"] == "healthy"
