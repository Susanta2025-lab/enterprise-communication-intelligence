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
    assert "/api/v1/workflow-actions" in schema["paths"]
    assert "/api/v1/workflow-actions/{action_id}" in schema["paths"]
    assert "/api/v1/workflow-actions/{action_id}/approve" in schema["paths"]
    assert "/api/v1/workflow-actions/{action_id}/reject" in schema["paths"]
    assert "/api/v1/workflow-actions/{action_id}/execute" in schema["paths"]

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

    workflow_collection = schema["paths"]["/api/v1/workflow-actions"]
    workflow_item = schema["paths"]["/api/v1/workflow-actions/{action_id}"]
    workflow_approve = schema["paths"]["/api/v1/workflow-actions/{action_id}/approve"]
    workflow_reject = schema["paths"]["/api/v1/workflow-actions/{action_id}/reject"]
    workflow_execute = schema["paths"]["/api/v1/workflow-actions/{action_id}/execute"]
    assert "post" in workflow_collection
    assert "get" in workflow_collection
    assert "patch" not in workflow_collection
    assert "delete" not in workflow_collection
    assert "get" in workflow_item
    assert "patch" not in workflow_item
    assert "delete" not in workflow_item
    assert "post" in workflow_approve
    assert "post" in workflow_reject
    assert "post" in workflow_execute
    assert "requestBody" not in workflow_approve["post"]
    assert "requestBody" not in workflow_reject["post"]
    assert "requestBody" not in workflow_execute["post"]
    assert "201" in workflow_collection["post"]["responses"]
    assert "401" in workflow_collection["post"]["responses"]
    assert "403" in workflow_collection["post"]["responses"]
    assert "404" in workflow_collection["post"]["responses"]
    assert "409" in workflow_collection["post"]["responses"]
    assert "503" in workflow_collection["post"]["responses"]
    assert "200" in workflow_collection["get"]["responses"]
    assert "401" in workflow_collection["get"]["responses"]
    assert "403" in workflow_collection["get"]["responses"]
    assert "503" in workflow_collection["get"]["responses"]
    assert "200" in workflow_item["get"]["responses"]
    assert "401" in workflow_item["get"]["responses"]
    assert "403" in workflow_item["get"]["responses"]
    assert "404" in workflow_item["get"]["responses"]
    assert "503" in workflow_item["get"]["responses"]
    assert "200" in workflow_approve["post"]["responses"]
    assert "401" in workflow_approve["post"]["responses"]
    assert "403" in workflow_approve["post"]["responses"]
    assert "404" in workflow_approve["post"]["responses"]
    assert "409" in workflow_approve["post"]["responses"]
    assert "503" in workflow_approve["post"]["responses"]
    assert "200" in workflow_reject["post"]["responses"]
    assert "401" in workflow_reject["post"]["responses"]
    assert "403" in workflow_reject["post"]["responses"]
    assert "404" in workflow_reject["post"]["responses"]
    assert "409" in workflow_reject["post"]["responses"]
    assert "503" in workflow_reject["post"]["responses"]
    assert "200" in workflow_execute["post"]["responses"]
    assert "401" in workflow_execute["post"]["responses"]
    assert "403" in workflow_execute["post"]["responses"]
    assert "404" in workflow_execute["post"]["responses"]
    assert "409" in workflow_execute["post"]["responses"]
    assert "503" in workflow_execute["post"]["responses"]
    assert "/api/v1/workflow-actions/{action_id}/retry" not in schema["paths"]

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


def test_openapi_schema_exposes_workflow_action_routes(client: TestClient) -> None:
    """Phase 11C/12E expose proposal, approval, and execute without retry."""
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/workflow-actions" in paths
    assert "/api/v1/workflow-actions/{action_id}" in paths
    assert "/api/v1/workflow-actions/{action_id}/approve" in paths
    assert "/api/v1/workflow-actions/{action_id}/reject" in paths
    assert "/api/v1/workflow-actions/{action_id}/execute" in paths
    assert "/api/v1/workflow-actions/{action_id}/retry" not in paths
    assert "post" in paths["/api/v1/workflow-actions"]
    assert "get" in paths["/api/v1/workflow-actions"]
    assert "get" in paths["/api/v1/workflow-actions/{action_id}"]
    assert "post" in paths["/api/v1/workflow-actions/{action_id}/approve"]
    assert "post" in paths["/api/v1/workflow-actions/{action_id}/reject"]
    assert "post" in paths["/api/v1/workflow-actions/{action_id}/execute"]
    assert "requestBody" not in paths["/api/v1/workflow-actions/{action_id}/execute"]["post"]
    for path, operations in paths.items():
        if "workflow-actions" not in path:
            continue
        assert "patch" not in operations
        assert "delete" not in operations
        assert "put" not in operations


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
