"""PostgreSQL readiness probe against the ephemeral test database."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.infrastructure.storage.runtime import (
    dispose_persistence_runtime,
    probe_database_readiness,
)
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
def postgres_client(
    monkeypatch: pytest.MonkeyPatch,
    postgres_test_url: str,
) -> Iterator[TestClient]:
    """TestClient with DATABASE_URL pointing at the guarded PostgreSQL test database."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", postgres_test_url)
    get_settings.cache_clear()
    dispose_persistence_runtime()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        dispose_persistence_runtime()
        get_settings.cache_clear()


def test_probe_database_readiness_succeeds(postgres_test_url: str) -> None:
    """The infrastructure probe should succeed against the migrated test database."""
    dispose_persistence_runtime()
    try:
        assert probe_database_readiness(postgres_test_url) is True
    finally:
        dispose_persistence_runtime()


def test_readiness_endpoint_succeeds_when_database_configured(
    postgres_client: TestClient,
) -> None:
    """GET /api/v1/readiness returns 200 when the test database answers SELECT 1."""
    response = postgres_client.get("/api/v1/readiness")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ready"}
    text = response.text.lower()
    assert "password" not in text
    assert "postgresql" not in text


def test_health_endpoints_do_not_query_database(postgres_client: TestClient) -> None:
    """Process health remains 200 independently of the readiness database probe."""
    root = postgres_client.get("/health")
    versioned = postgres_client.get("/api/v1/health")
    assert root.status_code == 200
    assert root.json() == {"status": "healthy"}
    assert versioned.status_code == 200
    assert versioned.json()["status"] == "healthy"
