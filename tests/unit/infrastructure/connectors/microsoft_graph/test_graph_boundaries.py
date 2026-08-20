"""Architecture boundary tests for the Microsoft Graph REST adapter."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_GRAPH_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors" / "microsoft_graph"
_COMMON_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors" / "common"
_DOMAIN_ROOT = _REPO_ROOT / "app" / "domain"
_APPLICATION_ROOT = _REPO_ROOT / "app" / "application"
_FORBIDDEN_SDK = (
    "msgraph",
    "azure.identity",
    "azure_identity",
    "msal",
    "msal_extensions",
    "kiota",
)
_FORBIDDEN_COUPLING = (
    "ConnectorAccountService",
    "ConnectorAccountRepository",
    "PersistenceUnitOfWork",
    "sqlalchemy",
    "fastapi",
    "alembic",
    "AIProvider",
    "CommunicationAnalysisService",
    "CommunicationAnalysisWorkflowService",
    "AnalysisRepository",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_graph_adapter_does_not_use_microsoft_sdk() -> None:
    for path in _python_files(_GRAPH_ROOT):
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        for marker in _FORBIDDEN_SDK:
            assert marker.lower() not in lowered, f"{path} must not reference {marker}"


def test_graph_adapter_does_not_couple_to_accounts_api_or_ai() -> None:
    for path in _python_files(_GRAPH_ROOT):
        source = path.read_text(encoding="utf-8")
        for marker in _FORBIDDEN_COUPLING:
            assert marker not in source, f"{path} must not reference {marker}"


def test_graph_adapter_does_not_log_sensitive_fields() -> None:
    for path in _python_files(_GRAPH_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "logger.exception" not in source
        assert "exc_info" not in source
        assert "response.text" not in source
        assert "response.content" not in source
        assert "str(exc)" not in source
        assert "repr(exc)" not in source
        assert "print(" not in source


def test_graph_adapter_does_not_implement_oauth() -> None:
    for path in _python_files(_GRAPH_ROOT):
        source = path.read_text(encoding="utf-8").lower()
        assert "authorization_code" not in source
        assert "refresh_token" not in source
        assert "client_secret" not in source
        assert "client_id" not in source
        assert "tenant_id" not in source
        assert "device_code" not in source
        assert "pkce" not in source


def test_domain_and_application_do_not_import_graph_adapter() -> None:
    marker = "infrastructure.connectors.microsoft_graph"
    for root in (_DOMAIN_ROOT, _APPLICATION_ROOT):
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert marker not in source, f"{path} must stay Graph-adapter-agnostic"


def test_common_connector_helpers_do_not_use_graph_sdk() -> None:
    for path in _python_files(_COMMON_ROOT):
        source = path.read_text(encoding="utf-8").lower()
        for marker in _FORBIDDEN_SDK:
            assert marker.lower() not in source
        assert "graph.microsoft.com" not in source
        assert "microsoft_graph" not in source
