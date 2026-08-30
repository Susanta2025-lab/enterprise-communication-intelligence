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
    """Executors and connectors remain OAuth-unaware AccessTokenProvider consumers."""
    from app.infrastructure.connectors.gmail import GmailCommunicationConnector
    from app.infrastructure.connectors.microsoft_graph import (
        MicrosoftGraphCommunicationConnector,
    )
    from app.infrastructure.executors.gmail import GmailCommunicationActionExecutor
    from app.infrastructure.executors.microsoft_graph import (
        MicrosoftGraphCommunicationActionExecutor,
    )

    assert GmailCommunicationConnector.__name__ == "GmailCommunicationConnector"
    assert MicrosoftGraphCommunicationConnector.__name__ == ("MicrosoftGraphCommunicationConnector")
    assert GmailCommunicationActionExecutor.__name__ == "GmailCommunicationActionExecutor"
    assert MicrosoftGraphCommunicationActionExecutor.__name__ == (
        "MicrosoftGraphCommunicationActionExecutor"
    )
    for path in (
        _ROOT / "app" / "infrastructure" / "executors" / "gmail.py",
        _ROOT / "app" / "infrastructure" / "executors" / "microsoft_graph.py",
        _ROOT / "app" / "infrastructure" / "connectors" / "gmail" / "connector.py",
        _ROOT / "app" / "infrastructure" / "connectors" / "microsoft_graph" / "connector.py",
        _ROOT / "app" / "domain" / "interfaces" / "communication_action_executor.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "MailboxAuthorizationSession" not in source
        assert "granted_capabilities" not in source
        assert "REAUTH_REQUIRED" not in source
        assert "credential_ref" not in source
    resolver = (
        _ROOT / "app" / "domain" / "interfaces" / "communication_credential_resolver.py"
    ).read_text(encoding="utf-8")
    assert "MailboxAuthorizationSession" not in resolver
    assert "granted_capabilities" not in resolver
    assert "REAUTH_REQUIRED" not in resolver
    assert "credential_ref" in resolver
    assert "AccessTokenProvider" in resolver
    execution = (
        _ROOT / "app" / "application" / "services" / "workflow_action_execution.py"
    ).read_text(encoding="utf-8")
    assert "MailboxAuthorizationSession" not in execution
    assert "mark_reauth_required_owned" in execution
    assert "granted_capabilities" in execution


def test_gmail_and_microsoft_oauth_routes_exist() -> None:
    """13C/13D publish Gmail and Microsoft mailbox OAuth HTTP."""
    gmail_route = (_ROOT / "app" / "api" / "routes" / "gmail_oauth.py").read_text(encoding="utf-8")
    assert "/connector-accounts/gmail/authorize" in gmail_route
    assert "/connector-accounts/gmail/authorize/another" in gmail_route
    assert "/oauth/callbacks/gmail" in gmail_route
    assert "require_authenticated_communications_connect" in gmail_route
    assert "get_gmail_mailbox_oauth_callback_service" in gmail_route
    assert "login.microsoftonline.com" not in gmail_route.lower()
    microsoft_route = (_ROOT / "app" / "api" / "routes" / "microsoft_oauth.py").read_text(
        encoding="utf-8"
    )
    assert "/connector-accounts/microsoft_graph/authorize" in microsoft_route
    assert "/connector-accounts/microsoft_graph/authorize/another" in microsoft_route
    assert "/oauth/callbacks/microsoft_graph" in microsoft_route
    assert "require_authenticated_communications_connect" in microsoft_route
    assert "get_microsoft_mailbox_oauth_callback_service" in microsoft_route
    router = (_ROOT / "app" / "api" / "router.py").read_text(encoding="utf-8")
    assert "gmail_oauth" in router
    assert "microsoft_oauth" in router
    assert "connector_accounts" in router
    lifecycle = (_ROOT / "app" / "api" / "routes" / "connector_accounts.py").read_text(
        encoding="utf-8"
    )
    assert "/connector-accounts/{connector_account_id}/disconnect" in lifecycle
    assert "/connector-accounts/{connector_account_id}/reauthorize" in lifecycle
    assert '    "/connector-accounts",' in lifecycle or '"/connector-accounts"' in lifecycle
    assert "require_authenticated_communications_connect" in lifecycle
    assert "require_authenticated_communications_read" in lifecycle


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
        assert "external_account_id" not in source
