"""Boundary tests: analysis orchestration must not create workflow actions."""

from pathlib import Path

from app.application.services.workflow_action_execution import WorkflowActionExecutionService
from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor
from app.domain.interfaces.communication_connector import CommunicationConnector
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.infrastructure.executors.fake import FakeCommunicationActionExecutor

_ROOT = Path(__file__).resolve().parents[3]
_SERVICES = _ROOT / "app" / "application" / "services"
_API_ROUTES = _ROOT / "app" / "api" / "routes"
_ANALYSIS_MODULES = (
    "communication_analysis.py",
    "communication_analysis_workflow.py",
    "communication_ingestion.py",
    "analysis_history.py",
)
_WRITE_MARKERS = (
    "users.messages.send",
    "gmail.send",
    "sendMail",
    "createReply",
    "Mail.Send",
    "Mail.ReadWrite",
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
    assert "FakeCommunicationActionExecutor" not in source
    assert "WorkflowActionExecutionService" not in source
    assert "def execute(" not in source
    assert "sqlalchemy" not in source
    assert "fastapi" not in source


def test_workflow_api_exposes_execute_without_retry() -> None:
    """Phase 12E exposes execute over HTTP; retry remains absent."""
    workflow_routes = (_API_ROUTES / "workflow_actions.py").read_text(encoding="utf-8")
    assert "workflow-actions" in workflow_routes
    assert "WorkflowActionService" in workflow_routes
    assert "WorkflowActionExecutionService" in workflow_routes
    assert "/execute" in workflow_routes
    assert "/retry" not in workflow_routes
    assert "GmailCommunicationConnector" not in workflow_routes
    assert "MicrosoftGraphCommunicationConnector" not in workflow_routes
    assert "GmailCommunicationActionExecutor" not in workflow_routes
    assert "MicrosoftGraphCommunicationActionExecutor" not in workflow_routes
    assert "sqlalchemy" not in workflow_routes

    communications = (_API_ROUTES / "communications.py").read_text(encoding="utf-8")
    analyses = (_API_ROUTES / "analyses.py").read_text(encoding="utf-8")
    assert "WorkflowAction" not in communications
    assert "WorkflowActionService" not in communications
    assert "WorkflowAction" not in analyses
    assert "WorkflowActionService" not in analyses

    router = (_ROOT / "app" / "api" / "router.py").read_text(encoding="utf-8")
    assert "workflow_actions" in router
    dependencies = (_ROOT / "app" / "api" / "dependencies.py").read_text(encoding="utf-8")
    assert "get_workflow_action_execution_service" in dependencies
    assert "WorkflowActionExecutionService" in dependencies
    assert "require_authenticated_communications_send" in dependencies
    assert "GmailCommunicationActionExecutor" not in dependencies
    assert "MicrosoftGraphCommunicationActionExecutor" not in dependencies


def test_communications_send_permission_is_isolated_from_application_services() -> None:
    """communications:send belongs to security and the execute route, not application services."""
    services = _SERVICES
    for path in services.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "communications:send" not in source, f"{path} must not hard-code send permission"
    domain = _ROOT / "app" / "domain"
    for path in domain.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "communications:send" not in source, f"{path} must not hard-code send permission"
    security = (_ROOT / "app" / "core" / "security.py").read_text(encoding="utf-8")
    assert 'COMMUNICATIONS_SEND_PERMISSION = "communications:send"' in security


def test_communication_connector_remains_read_only() -> None:
    """The fetch port still has no send or reply operations."""
    assert not hasattr(CommunicationConnector, "send")
    assert not hasattr(CommunicationConnector, "reply")
    assert not hasattr(CommunicationConnector, "execute")
    names = set(CommunicationConnector.__abstractmethods__)
    assert names == {"provider", "list_messages", "fetch_message"}


def test_gmail_and_graph_adapters_remain_read_only() -> None:
    """Vendor adapters still expose only list/fetch; no send or reply writes."""
    assert not hasattr(GmailCommunicationConnector, "send")
    assert not hasattr(GmailCommunicationConnector, "reply")
    assert not hasattr(GmailCommunicationConnector, "execute")
    assert not hasattr(MicrosoftGraphCommunicationConnector, "send")
    assert not hasattr(MicrosoftGraphCommunicationConnector, "reply")
    assert not hasattr(MicrosoftGraphCommunicationConnector, "execute")
    connectors = _ROOT / "app" / "infrastructure" / "connectors"
    for path in connectors.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for marker in _WRITE_MARKERS:
            assert marker not in source, f"{path} must not add {marker}"


def test_execution_boundary_uses_factory_and_unchanged_command() -> None:
    """Phase 12E routes through a factory; the execution command stays unchanged."""
    assert (_ROOT / "app" / "domain" / "interfaces" / "communication_action_executor.py").is_file()
    assert (
        _ROOT / "app" / "domain" / "interfaces" / "communication_action_executor_factory.py"
    ).is_file()
    assert (_ROOT / "app" / "infrastructure" / "executors" / "fake.py").is_file()
    assert (_ROOT / "app" / "infrastructure" / "executors" / "factory.py").is_file()
    assert (_SERVICES / "workflow_action_execution.py").is_file()
    assert CommunicationActionExecutor is not CommunicationConnector
    assert issubclass(FakeCommunicationActionExecutor, CommunicationActionExecutor)
    assert hasattr(WorkflowActionExecutionService, "execute")
    assert set(CommunicationActionExecution.model_fields) == {
        "action_id",
        "action_type",
        "approved_reply_body",
        "connector_account_id",
        "provider_message_id",
        "provider",
    }

    execution_source = (_SERVICES / "workflow_action_execution.py").read_text(encoding="utf-8")
    assert "CommunicationActionExecutor" in execution_source
    assert "CommunicationActionExecutorFactory" in execution_source
    assert "AIProvider" not in execution_source
    assert "AnalysisHistoryService" not in execution_source
    assert "analysis_repository" not in execution_source
    assert "GmailCommunicationConnector" not in execution_source
    assert "MicrosoftGraphCommunicationConnector" not in execution_source
    assert "GmailCommunicationActionExecutor" not in execution_source
    assert "MicrosoftGraphCommunicationActionExecutor" not in execution_source
    assert "CommunicationCredentialResolver" not in execution_source
    assert "EnvironmentCommunicationCredentialResolver" not in execution_source
    assert "AccessTokenProvider" not in execution_source
    assert "credential_ref" not in execution_source
    assert "sqlalchemy" not in execution_source
    assert "fastapi" not in execution_source
    assert "EXECUTION_UNKNOWN" not in execution_source
    assert "retry" not in execution_source.lower()
    assert "outbox" not in execution_source.lower()

    factory_source = (_ROOT / "app" / "infrastructure" / "executors" / "factory.py").read_text(
        encoding="utf-8"
    )
    assert "EXECUTION_UNKNOWN" not in factory_source
    assert "retry" not in factory_source.lower()
    assert "tenacity" not in factory_source.lower()
    graph_source = (
        _ROOT / "app" / "infrastructure" / "executors" / "microsoft_graph.py"
    ).read_text(encoding="utf-8")
    gmail_source = (_ROOT / "app" / "infrastructure" / "executors" / "gmail.py").read_text(
        encoding="utf-8"
    )
    credentials_source = (
        _ROOT / "app" / "infrastructure" / "credentials" / "environment.py"
    ).read_text(encoding="utf-8")
    for source in (graph_source, gmail_source, credentials_source):
        assert "EXECUTION_UNKNOWN" not in source
        assert "tenacity" not in source.lower()
        assert "retry-after" not in source.lower()

    fake_source = (_ROOT / "app" / "infrastructure" / "executors" / "fake.py").read_text(
        encoding="utf-8"
    )
    assert "FakeCommunicationActionExecutor" in fake_source
    assert "CommunicationCredentialResolver" not in fake_source
    assert "AccessTokenProvider" not in fake_source
    assert "credential_ref" not in fake_source
    providers = _ROOT / "app" / "providers"
    for path in providers.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "FakeCommunicationActionExecutor" not in source
        assert "CommunicationActionExecutor" not in source
    connectors = _ROOT / "app" / "infrastructure" / "connectors"
    for path in connectors.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "FakeCommunicationActionExecutor" not in source
        assert "CommunicationActionExecutor" not in source
