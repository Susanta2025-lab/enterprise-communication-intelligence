"""Architecture boundary tests for Phase 13A mailbox OAuth foundation."""

from pathlib import Path

from app.application.services.mailbox_authorization_sessions import (
    MailboxAuthorizationStartResult,
)
from app.domain.interfaces.communication_action_executor import CommunicationActionExecution
from app.domain.interfaces.communication_credential_resolver import AccessTokenProvider
from app.domain.interfaces.mailbox_authorization_session_repository import (
    ConsumedMailboxAuthorizationSession,
    MailboxAuthorizationSessionRecord,
    NewMailboxAuthorizationSession,
)

_ROOT = Path(__file__).resolve().parents[3]
_SQLALCHEMY_FREE = (
    _ROOT / "app" / "domain",
    _ROOT / "app" / "application",
)
_TOKEN_FIELDS = (
    "access_token",
    "refresh_token",
    "authorization_code",
    "client_secret",
    "id_token",
    "credential_ref",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_application_and_domain_do_not_import_sqlalchemy_or_oauth_sdks() -> None:
    """Mailbox OAuth foundation stays provider-SDK and SQLAlchemy free above infrastructure."""
    for root in _SQLALCHEMY_FREE:
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert "import sqlalchemy" not in source, f"{path} must not import SQLAlchemy"
            assert "from sqlalchemy" not in source, f"{path} must not import SQLAlchemy"
            for marker in (
                "import msal",
                "from msal",
                "import google.auth",
                "from google.auth",
                "import google_auth_oauthlib",
                "from google_auth_oauthlib",
                "import azure.keyvault",
                "from azure.keyvault",
                "import boto3",
                "from boto3",
            ):
                assert marker not in source, f"{path} must not import {marker}"


def test_authorization_session_records_have_no_token_fields() -> None:
    """Sessions persist consent metadata, not tokens or locators."""
    for cls in (
        NewMailboxAuthorizationSession,
        MailboxAuthorizationSessionRecord,
        ConsumedMailboxAuthorizationSession,
        MailboxAuthorizationStartResult,
    ):
        fields = set(cls.__dataclass_fields__)
        assert fields.isdisjoint(_TOKEN_FIELDS), cls.__name__
        assert "state" not in fields or cls is MailboxAuthorizationStartResult
        if cls is MailboxAuthorizationStartResult:
            assert "state" in fields
            assert "pkce_verifier" not in fields
        if cls is MailboxAuthorizationSessionRecord:
            assert "state_hash" in fields
            assert "state" not in fields


def test_communication_action_execution_is_unchanged() -> None:
    """Phase 12 execution command remains free of OAuth fields."""
    assert set(CommunicationActionExecution.model_fields) == {
        "action_id",
        "action_type",
        "approved_reply_body",
        "connector_account_id",
        "provider_message_id",
        "provider",
    }
    assert AccessTokenProvider is not None


def test_gmail_and_graph_executors_and_connectors_are_unchanged() -> None:
    """13A does not modify production write or read adapters."""
    from app.infrastructure.connectors.gmail import GmailCommunicationConnector
    from app.infrastructure.connectors.microsoft_graph import (
        MicrosoftGraphCommunicationConnector,
    )
    from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
    from app.infrastructure.executors.microsoft_graph import (
        MicrosoftGraphCommunicationActionExecutor,
    )

    assert GmailCommunicationConnector.__name__ == "GmailCommunicationConnector"
    assert MicrosoftGraphCommunicationConnector.__name__ == (
        "MicrosoftGraphCommunicationConnector"
    )
    assert GmailCommunicationActionExecutor.__name__ == "GmailCommunicationActionExecutor"
    assert MicrosoftGraphCommunicationActionExecutor.__name__ == (
        "MicrosoftGraphCommunicationActionExecutor"
    )
    for path in (
        _ROOT / "app" / "infrastructure" / "executors" / "gmail.py",
        _ROOT / "app" / "infrastructure" / "executors" / "microsoft_graph.py",
        _ROOT / "app" / "infrastructure" / "connectors" / "gmail" / "connector.py",
        _ROOT / "app" / "infrastructure" / "connectors" / "microsoft_graph" / "connector.py",
        _ROOT / "app" / "application" / "services" / "workflow_action_execution.py",
        _ROOT / "app" / "domain" / "interfaces" / "communication_action_executor.py",
        _ROOT / "app" / "domain" / "interfaces" / "communication_credential_resolver.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "MailboxAuthorizationSession" not in source
        assert "granted_capabilities" not in source
        assert "REAUTH_REQUIRED" not in source


def test_no_public_oauth_authorize_or_callback_routes() -> None:
    """13A does not publish incomplete provider OAuth HTTP endpoints."""
    routes = _ROOT / "app" / "api" / "routes"
    for path in _python_files(routes):
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        assert "mailbox_authorization" not in lowered
        assert "oauth" not in lowered
        assert "accounts.google.com" not in lowered
        assert "login.microsoftonline.com" not in lowered
    router = (_ROOT / "app" / "api" / "router.py").read_text(encoding="utf-8")
    assert "oauth" not in router.lower()
    assert "mailbox_authorization" not in router


def test_future_oauth_contracts_reject_client_supplied_credential_ref() -> None:
    """Start/consume results and session records must not accept credential_ref."""
    assert "credential_ref" not in MailboxAuthorizationStartResult.__dataclass_fields__
    assert "credential_ref" not in ConsumedMailboxAuthorizationSession.__dataclass_fields__
    assert "credential_ref" not in NewMailboxAuthorizationSession.__dataclass_fields__
    schemas = _ROOT / "app" / "schemas"
    for path in _python_files(schemas):
        source = path.read_text(encoding="utf-8")
        assert "credential_ref" not in source
        assert "refresh_token" not in source
        assert "access_token" not in source
