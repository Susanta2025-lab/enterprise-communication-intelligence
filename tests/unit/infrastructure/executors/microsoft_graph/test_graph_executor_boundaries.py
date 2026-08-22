"""Architecture boundary tests for the Microsoft Graph reply executor."""

from pathlib import Path

from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor
from app.domain.interfaces.communication_connector import CommunicationConnector
from app.infrastructure.connectors.microsoft_graph import MicrosoftGraphCommunicationConnector
from app.infrastructure.executors.microsoft_graph import MicrosoftGraphCommunicationActionExecutor

_REPO_ROOT = Path(__file__).resolve().parents[5]
_EXECUTOR_ROOT = _REPO_ROOT / "app" / "infrastructure" / "executors"
_GRAPH_EXECUTOR = _EXECUTOR_ROOT / "microsoft_graph.py"
_FAKE_EXECUTOR = _EXECUTOR_ROOT / "fake.py"
_CONNECTOR_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors"
_APPLICATION_ROOT = _REPO_ROOT / "app" / "application"
_API_ROOT = _REPO_ROOT / "app" / "api"
_DOMAIN_COMMAND = (
    _REPO_ROOT / "app" / "domain" / "interfaces" / "communication_action_executor.py"
)
_FORBIDDEN_SDK = (
    "msgraph",
    "azure.identity",
    "azure_identity",
    "msal",
    "msal_extensions",
    "kiota",
    "DefaultAzureCredential",
    "InteractiveBrowserCredential",
    "DeviceCodeCredential",
)
_FORBIDDEN_COUPLING = (
    "EnvironmentCommunicationCredentialResolver",
    "CommunicationCredentialResolver",
    "credential_ref",
    "ConnectorAccount",
    "ConnectorAccountRepository",
    "WorkflowActionExecutionService",
    "fastapi",
    "sqlalchemy",
    "alembic",
    "AIProvider",
    "os.environ",
    "MicrosoftGraphCommunicationConnector",
)
_FORBIDDEN_OPERATIONS = (
    "sendMail",
    "createReply",
    "replyAll",
    "Mail.ReadWrite",
)
_SECRET_LOG_MARKERS = (
    "approved_reply_body=",
    "access_token=",
    "provider_message_id=",
    "credential_ref=",
    "response.text",
    "response.content",
    "response.json(",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_communication_connector_remains_read_only() -> None:
    assert not hasattr(CommunicationConnector, "send")
    assert not hasattr(CommunicationConnector, "reply")
    assert not hasattr(CommunicationConnector, "execute")
    assert set(CommunicationConnector.__abstractmethods__) == {
        "provider",
        "list_messages",
        "fetch_message",
    }


def test_graph_read_adapter_has_no_reply_or_send() -> None:
    assert not hasattr(MicrosoftGraphCommunicationConnector, "send")
    assert not hasattr(MicrosoftGraphCommunicationConnector, "reply")
    assert not hasattr(MicrosoftGraphCommunicationConnector, "execute")
    source = (
        _CONNECTOR_ROOT / "microsoft_graph" / "connector.py"
    ).read_text(encoding="utf-8")
    for marker in ("sendMail", "createReply", "replyAll", "/reply"):
        assert marker not in source


def test_graph_executor_implements_write_port() -> None:
    assert issubclass(MicrosoftGraphCommunicationActionExecutor, CommunicationActionExecutor)
    assert not issubclass(MicrosoftGraphCommunicationActionExecutor, CommunicationConnector)


def test_graph_executor_does_not_import_environment_resolver_or_credential_ref() -> None:
    source = _GRAPH_EXECUTOR.read_text(encoding="utf-8")
    for marker in _FORBIDDEN_COUPLING:
        assert marker not in source, f"graph executor must not reference {marker}"
    assert "infrastructure.credentials" not in source
    assert "infrastructure.connectors.microsoft_graph" not in source


def test_graph_executor_does_not_use_microsoft_sdk() -> None:
    source = _GRAPH_EXECUTOR.read_text(encoding="utf-8").lower()
    for marker in _FORBIDDEN_SDK:
        assert marker.lower() not in source, f"graph executor must not reference {marker}"


def test_graph_executor_does_not_use_sendmail_or_createreply() -> None:
    source = _GRAPH_EXECUTOR.read_text(encoding="utf-8")
    for marker in _FORBIDDEN_OPERATIONS:
        assert marker not in source, f"graph executor must not use {marker}"
    assert "/me/messages/" in source
    assert "/reply" in source
    assert "sendMail" not in source


def test_graph_executor_does_not_log_sensitive_fields() -> None:
    source = _GRAPH_EXECUTOR.read_text(encoding="utf-8")
    assert "logger.exception" not in source
    assert "exc_info" not in source
    assert "print(" not in source
    for marker in _SECRET_LOG_MARKERS:
        assert marker not in source, f"graph executor must not log {marker}"


def test_graph_executor_does_not_implement_oauth() -> None:
    source = _GRAPH_EXECUTOR.read_text(encoding="utf-8").lower()
    assert "authorization_code" not in source
    assert "refresh_token" not in source
    assert "client_secret" not in source
    assert "client_id" not in source
    assert "tenant_id" not in source
    assert "device_code" not in source
    assert "pkce" not in source


def test_graph_executor_does_not_retry() -> None:
    source = _GRAPH_EXECUTOR.read_text(encoding="utf-8").lower()
    assert "retry" not in source
    assert "backoff" not in source
    assert "sleep" not in source
    assert "httpx.httptransport" not in source.replace(" ", "")


def test_application_does_not_import_graph_executor() -> None:
    marker = "MicrosoftGraphCommunicationActionExecutor"
    for path in _python_files(_APPLICATION_ROOT):
        source = path.read_text(encoding="utf-8")
        assert marker not in source, f"{path} must not import the Graph executor"
        assert "infrastructure.executors.microsoft_graph" not in source


def test_api_does_not_import_graph_executor() -> None:
    marker = "MicrosoftGraphCommunicationActionExecutor"
    for path in _python_files(_API_ROOT):
        source = path.read_text(encoding="utf-8")
        assert marker not in source, f"{path} must not import the Graph executor"


def test_execution_command_has_no_token_or_credential_ref() -> None:
    assert set(CommunicationActionExecution.model_fields) == {
        "action_id",
        "action_type",
        "approved_reply_body",
        "connector_account_id",
        "provider_message_id",
        "provider",
    }
    source = _DOMAIN_COMMAND.read_text(encoding="utf-8")
    assert "credential_ref" not in source
    assert "access_token" not in source
    assert "refresh_token" not in source
    assert "owner_user_id" not in source


def test_routed_executor_is_absent() -> None:
    names = {path.name for path in _python_files(_EXECUTOR_ROOT)}
    assert "microsoft_graph.py" in names
    assert "gmail.py" in names
    assert "fake.py" in names
    for path in _python_files(_EXECUTOR_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "RoutedCommunicationActionExecutor" not in source
        assert "ACTION_EXECUTOR" not in source


def test_fake_executor_remains_credential_independent() -> None:
    source = _FAKE_EXECUTOR.read_text(encoding="utf-8")
    assert "AccessTokenProvider" not in source
    assert "credential_ref" not in source
    assert "httpx" not in source
    assert "MicrosoftGraphCommunicationActionExecutor" not in source
