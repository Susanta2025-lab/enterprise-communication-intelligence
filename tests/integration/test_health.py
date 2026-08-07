"""Integration tests for health and readiness endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

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
