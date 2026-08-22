"""Architecture boundary tests for mailbox credential resolution."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CREDENTIALS_ROOT = _REPO_ROOT / "app" / "infrastructure" / "credentials"
_DOMAIN_ROOT = _REPO_ROOT / "app" / "domain"
_APPLICATION_ROOT = _REPO_ROOT / "app" / "application"
_API_ROOT = _REPO_ROOT / "app" / "api"
_FORBIDDEN_SDK = (
    "googleapiclient",
    "google.auth",
    "google.oauth",
    "msgraph",
    "azure.identity",
    "azure.keyvault",
    "msal",
    "boto3",
    "botocore",
    "secretsmanager",
    "DefaultAzureCredential",
)
_FORBIDDEN_COUPLING = (
    "WorkflowActionExecutionService",
    "FakeCommunicationActionExecutor",
    "GmailCommunicationConnector",
    "MicrosoftGraphCommunicationConnector",
    "ConnectorAccountService",
    "fastapi",
    "sqlalchemy",
    "AIProvider",
)
_WRITE_MARKERS = (
    "users.messages.send",
    "sendMail",
    "createReply",
)
_SECRET_LOG_MARKERS = (
    "credential_ref=",
    "access_token=",
    "refresh_token",
    "Authorization",
)
_CONNECTOR_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors"
_EXECUTOR_ROOT = _REPO_ROOT / "app" / "infrastructure" / "executors"
_DOMAIN_RESOLVER = (
    _REPO_ROOT / "app" / "domain" / "interfaces" / "communication_credential_resolver.py"
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_credentials_package_does_not_use_vendor_or_secret_sdks() -> None:
    for path in _python_files(_CREDENTIALS_ROOT):
        source = path.read_text(encoding="utf-8")
        for marker in _FORBIDDEN_SDK:
            assert marker not in source, f"{path} must not reference {marker}"


def test_credentials_package_does_not_couple_to_execution_or_api() -> None:
    for path in _python_files(_CREDENTIALS_ROOT):
        source = path.read_text(encoding="utf-8")
        for marker in _FORBIDDEN_COUPLING:
            assert marker not in source, f"{path} must not reference {marker}"
        for marker in _WRITE_MARKERS:
            assert marker not in source, f"{path} must not add {marker}"


def test_credentials_package_does_not_log_secret_fields() -> None:
    for path in _python_files(_CREDENTIALS_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "logger.exception" not in source
        assert "exc_info" not in source
        assert "print(" not in source
        for marker in _SECRET_LOG_MARKERS:
            assert marker not in source, f"{path} must not log {marker}"


def test_credentials_package_does_not_implement_oauth() -> None:
    for path in _python_files(_CREDENTIALS_ROOT):
        source = path.read_text(encoding="utf-8").lower()
        assert "authorization_code" not in source
        assert "refresh_token" not in source
        assert "client_secret" not in source
        assert "pkce" not in source


def test_application_and_api_do_not_import_environment_resolver() -> None:
    marker = "EnvironmentCommunicationCredentialResolver"
    for root in (_APPLICATION_ROOT, _API_ROOT):
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert marker not in source, f"{path} must not import the env resolver"


def test_domain_does_not_import_environment_resolver() -> None:
    for path in _python_files(_DOMAIN_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "EnvironmentCommunicationCredentialResolver" not in source
        assert "os.environ" not in source
        assert "infrastructure.credentials" not in source


def test_domain_resolver_port_stays_provider_neutral() -> None:
    source = _DOMAIN_RESOLVER.read_text(encoding="utf-8")
    assert "import os" not in source
    assert "fastapi" not in source
    assert "httpx" not in source
    assert "google" not in source.lower()
    assert "azure" not in source.lower()
    assert "boto" not in source.lower()
    assert "infrastructure" not in source
    assert "os.environ" not in source


def test_read_connectors_do_not_resolve_credential_ref() -> None:
    for path in _python_files(_CONNECTOR_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "credential_ref" not in source
        assert "CommunicationCredentialResolver" not in source
        assert "EnvironmentCommunicationCredentialResolver" not in source


def test_fake_executor_does_not_invoke_credential_resolver() -> None:
    for path in _python_files(_EXECUTOR_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "CommunicationCredentialResolver" not in source
        assert "AccessTokenProvider" not in source
        assert "credential_ref" not in source
        assert "EnvironmentCommunicationCredentialResolver" not in source


def test_production_write_executors_are_absent() -> None:
    names = {path.name for path in _python_files(_EXECUTOR_ROOT)}
    assert names == {"__init__.py", "fake.py"}
    for path in _python_files(_EXECUTOR_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "GmailCommunicationActionExecutor" not in source
        assert "MicrosoftGraphCommunicationActionExecutor" not in source
        assert "RoutedCommunicationActionExecutor" not in source


def test_credentials_package_does_not_use_external_account_id() -> None:
    for path in _python_files(_CREDENTIALS_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "external_account_id" not in source


def test_credential_ref_is_not_uniquely_constrained() -> None:
    from sqlalchemy import UniqueConstraint

    from app.infrastructure.storage.models import ConnectorAccount

    unique_column_sets = [
        tuple(column.name for column in constraint.columns)
        for constraint in ConnectorAccount.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert unique_column_sets
    for columns in unique_column_sets:
        assert "credential_ref" not in columns
    assert ("user_id", "provider", "external_account_id") in unique_column_sets
