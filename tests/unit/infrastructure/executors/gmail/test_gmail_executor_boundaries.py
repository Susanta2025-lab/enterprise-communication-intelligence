"""Architecture boundary tests for the Gmail reply executor."""

from pathlib import Path

from app.domain.interfaces import CommunicationActionExecution, CommunicationActionExecutor
from app.domain.interfaces.communication_connector import CommunicationConnector
from app.infrastructure.connectors.gmail import GmailCommunicationConnector
from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor

_REPO_ROOT = Path(__file__).resolve().parents[5]
_EXECUTOR_ROOT = _REPO_ROOT / "app" / "infrastructure" / "executors"
_GMAIL_EXECUTOR = _EXECUTOR_ROOT / "gmail.py"
_FAKE_EXECUTOR = _EXECUTOR_ROOT / "fake.py"
_CONNECTOR_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors"
_APPLICATION_ROOT = _REPO_ROOT / "app" / "application"
_API_ROOT = _REPO_ROOT / "app" / "api"
_DOMAIN_COMMAND = (
    _REPO_ROOT / "app" / "domain" / "interfaces" / "communication_action_executor.py"
)
_FORBIDDEN_SDK = (
    "googleapiclient",
    "google.auth",
    "google.oauth",
    "google_auth",
    "google-api-python-client",
    "InstalledAppFlow",
    "token.json",
    "credentials.json",
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
    "GmailCommunicationConnector",
)
_FORBIDDEN_OPERATIONS = (
    "users.drafts.create",
    "users.drafts.send",
    "drafts.create",
    "drafts.send",
    "replyAll",
    "reply-all",
)
_SECRET_LOG_MARKERS = (
    "approved_reply_body=",
    "access_token=",
    "provider_message_id=",
    "credential_ref=",
    "response.text",
    "response.content",
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


def test_gmail_read_adapter_has_no_reply_or_send() -> None:
    assert not hasattr(GmailCommunicationConnector, "send")
    assert not hasattr(GmailCommunicationConnector, "reply")
    assert not hasattr(GmailCommunicationConnector, "execute")
    source = (_CONNECTOR_ROOT / "gmail" / "connector.py").read_text(encoding="utf-8")
    for marker in ("users.messages.send", "drafts.send", "drafts.create", "/send"):
        assert marker not in source


def test_gmail_executor_implements_write_port() -> None:
    assert issubclass(GmailCommunicationActionExecutor, CommunicationActionExecutor)
    assert not issubclass(GmailCommunicationActionExecutor, CommunicationConnector)


def test_gmail_executor_does_not_import_environment_resolver_or_credential_ref() -> None:
    source = _GMAIL_EXECUTOR.read_text(encoding="utf-8")
    for marker in _FORBIDDEN_COUPLING:
        assert marker not in source, f"gmail executor must not reference {marker}"
    assert "infrastructure.credentials" not in source
    assert "infrastructure.connectors.gmail" not in source


def test_gmail_executor_does_not_use_google_sdk() -> None:
    source = _GMAIL_EXECUTOR.read_text(encoding="utf-8").lower()
    for marker in _FORBIDDEN_SDK:
        assert marker.lower() not in source, f"gmail executor must not reference {marker}"


def test_gmail_executor_does_not_use_drafts_or_reply_all() -> None:
    source = _GMAIL_EXECUTOR.read_text(encoding="utf-8")
    for marker in _FORBIDDEN_OPERATIONS:
        assert marker not in source, f"gmail executor must not use {marker}"
    assert "/users/me/messages" in source
    assert "/send" in source
    assert "metadata" in source


def test_gmail_executor_does_not_log_sensitive_fields() -> None:
    source = _GMAIL_EXECUTOR.read_text(encoding="utf-8")
    assert "logger.exception" not in source
    assert "exc_info" not in source
    assert "print(" not in source
    for marker in _SECRET_LOG_MARKERS:
        assert marker not in source, f"gmail executor must not log {marker}"


def test_gmail_executor_does_not_implement_oauth() -> None:
    source = _GMAIL_EXECUTOR.read_text(encoding="utf-8").lower()
    assert "authorization_code" not in source
    assert "refresh_token" not in source
    assert "client_secret" not in source
    assert "client_id" not in source
    assert "pkce" not in source


def test_gmail_executor_does_not_retry() -> None:
    source = _GMAIL_EXECUTOR.read_text(encoding="utf-8").lower()
    assert "retry" not in source
    assert "backoff" not in source
    assert "sleep" not in source
    assert "tenacity" not in source
    assert "httpx.httptransport" not in source.replace(" ", "")


def test_application_does_not_import_gmail_executor() -> None:
    marker = "GmailCommunicationActionExecutor"
    for path in _python_files(_APPLICATION_ROOT):
        source = path.read_text(encoding="utf-8")
        assert marker not in source, f"{path} must not import the Gmail executor"
        assert "infrastructure.executors.gmail" not in source


def test_api_does_not_import_gmail_executor() -> None:
    marker = "GmailCommunicationActionExecutor"
    for path in _python_files(_API_ROOT):
        source = path.read_text(encoding="utf-8")
        assert marker not in source, f"{path} must not import the Gmail executor"
        assert "communications:send" not in source


def test_execution_command_has_no_token_or_mailbox_identity() -> None:
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
    assert "external_account_id" not in source
    assert "mailbox_address" not in source
    assert "threadId" not in source


def test_routed_executor_is_absent() -> None:
    names = {path.name for path in _python_files(_EXECUTOR_ROOT)}
    assert "gmail.py" in names
    assert "microsoft_graph.py" in names
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
    assert "GmailCommunicationActionExecutor" not in source
