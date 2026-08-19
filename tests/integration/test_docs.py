"""Integration tests for OpenAPI documentation endpoints."""

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


def test_docs_available(client: TestClient) -> None:
    """Swagger UI should be available at /docs."""
    response = client.get("/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_openapi_schema_available(client: TestClient) -> None:
    """OpenAPI schema should be available at /openapi.json."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Enterprise Communication Intelligence Platform"
    assert schema["info"]["version"] == "0.1.0"
    assert "/health" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/readiness" in schema["paths"]
    assert "/api/v1/communications/analyze" in schema["paths"]
    assert "/api/v1/analyses" in schema["paths"]
    assert "/api/v1/analyses/{analysis_id}" in schema["paths"]

    analyze_operation = schema["paths"]["/api/v1/communications/analyze"]["post"]
    assert analyze_operation["summary"] == "Analyze a business communication"
    assert "requestBody" in analyze_operation
    assert "200" in analyze_operation["responses"]
    assert "401" in analyze_operation["responses"]
    assert "403" in analyze_operation["responses"]
    assert "500" in analyze_operation["responses"]
    assert "503" in analyze_operation["responses"]
    assert analyze_operation.get("security") == [{"HTTPBearer": []}]

    history_list = schema["paths"]["/api/v1/analyses"]["get"]
    history_get = schema["paths"]["/api/v1/analyses/{analysis_id}"]["get"]
    history_delete = schema["paths"]["/api/v1/analyses/{analysis_id}"]["delete"]
    assert "200" in history_list["responses"]
    assert "401" in history_list["responses"]
    assert "403" in history_list["responses"]
    assert "200" in history_get["responses"]
    assert "404" in history_get["responses"]
    assert "204" in history_delete["responses"]
    assert "404" in history_delete["responses"]

    serialized = repr(schema)
    assert "user_id" not in serialized
    assert "ExternalIdentity" not in serialized
    assert "sqlalchemy" not in serialized.lower()

    security_schemes = schema["components"]["securitySchemes"]
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"

def test_openapi_schema_exposes_analysis_history_routes(client: TestClient) -> None:
    """Phase 9B exposes owned analysis history endpoints."""
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/analyses" in paths
    assert "/api/v1/analyses/{analysis_id}" in paths
    assert "get" in paths["/api/v1/analyses"]
    assert "get" in paths["/api/v1/analyses/{analysis_id}"]
    assert "delete" in paths["/api/v1/analyses/{analysis_id}"]
    assert "post" not in paths["/api/v1/analyses"]
    assert "put" not in paths.get("/api/v1/analyses/{analysis_id}", {})
    assert "patch" not in paths.get("/api/v1/analyses/{analysis_id}", {})


def test_redoc_available(client: TestClient) -> None:
    """ReDoc should be available at /redoc in development."""
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_docs_are_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production must not expose OpenAPI or interactive docs."""
    for name in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://example.invalid/")
    monkeypatch.setenv("OIDC_AUDIENCE", "eci-api")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://eci_test:test@localhost:5432/eci_test",
    )
    get_settings.cache_clear()

    with TestClient(create_app()) as production_client:
        docs = production_client.get("/docs")
        redoc = production_client.get("/redoc")
        openapi = production_client.get("/openapi.json")

    assert docs.status_code == 404
    assert redoc.status_code == 404
    assert openapi.status_code == 404
