"""Boundary tests: analysis orchestration must not create workflow actions."""

from pathlib import Path

from app.domain.interfaces.communication_connector import CommunicationConnector

_ROOT = Path(__file__).resolve().parents[3]
_SERVICES = _ROOT / "app" / "application" / "services"
_API_ROUTES = _ROOT / "app" / "api" / "routes"
_ANALYSIS_MODULES = (
    "communication_analysis.py",
    "communication_analysis_workflow.py",
    "communication_ingestion.py",
    "analysis_history.py",
)


def test_analysis_services_do_not_import_workflow_action() -> None:
    """Analyze, persist-after-analyze, and ingestion must not create workflow actions."""
    for name in _ANALYSIS_MODULES:
        source = (_SERVICES / name).read_text(encoding="utf-8")
        assert "WorkflowAction" not in source, f"{name} must not reference WorkflowAction"
        assert "WorkflowActionStatus" not in source
        assert "WorkflowActionType" not in source


def test_workflow_action_service_does_not_import_connectors_or_ai() -> None:
    """WorkflowActionService stays on persistence ports; it does not send mail."""
    source = (_SERVICES / "workflow_actions.py").read_text(encoding="utf-8")
    assert "GmailCommunicationConnector" not in source
    assert "MicrosoftGraphCommunicationConnector" not in source
    assert "FakeCommunicationConnector" not in source
    assert "AIProvider" not in source
    assert "CommunicationActionExecutor" not in source
    assert "sqlalchemy" not in source
    assert "fastapi" not in source


def test_api_has_no_workflow_routes() -> None:
    """Phase 11B does not add HTTP workflow endpoints."""
    for path in _API_ROUTES.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "workflow-actions" not in source
        assert "WorkflowAction" not in source
        assert "WorkflowActionService" not in source


def test_communication_connector_remains_read_only() -> None:
    """The fetch port still has no send or reply operations."""
    assert not hasattr(CommunicationConnector, "send")
    assert not hasattr(CommunicationConnector, "reply")
    assert not hasattr(CommunicationConnector, "execute")
    names = set(CommunicationConnector.__abstractmethods__)
    assert names == {"provider", "list_messages", "fetch_message"}


def test_executor_module_is_absent() -> None:
    """CommunicationActionExecutor is out of scope for Phase 11B."""
    application = _ROOT / "app" / "application"
    domain_interfaces = _ROOT / "app" / "domain" / "interfaces"
    for root in (application, domain_interfaces):
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "CommunicationActionExecutor" not in source
            assert "FakeCommunicationActionExecutor" not in source
