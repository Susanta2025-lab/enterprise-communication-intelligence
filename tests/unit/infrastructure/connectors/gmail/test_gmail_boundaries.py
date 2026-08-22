"""Architecture boundary tests for the Gmail REST adapter."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_GMAIL_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors" / "gmail"
_COMMON_ROOT = _REPO_ROOT / "app" / "infrastructure" / "connectors" / "common"
_DOMAIN_ROOT = _REPO_ROOT / "app" / "domain"
_APPLICATION_ROOT = _REPO_ROOT / "app" / "application"
_FORBIDDEN_SDK = (
    "googleapiclient",
    "google.auth",
    "google.oauth",
    "google_auth",
    "InstalledAppFlow",
    "token.json",
    "credentials.json",
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
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_gmail_adapter_does_not_use_google_sdk() -> None:
    for path in _python_files(_GMAIL_ROOT):
        source = path.read_text(encoding="utf-8")
        lowered = source.lower()
        for marker in _FORBIDDEN_SDK:
            assert marker.lower() not in lowered, f"{path} must not reference {marker}"


def test_gmail_adapter_does_not_couple_to_accounts_or_api() -> None:
    for path in _python_files(_GMAIL_ROOT):
        source = path.read_text(encoding="utf-8")
        for marker in _FORBIDDEN_COUPLING:
            assert marker not in source, f"{path} must not reference {marker}"


def test_gmail_adapter_does_not_log_sensitive_fields() -> None:
    for path in _python_files(_GMAIL_ROOT):
        source = path.read_text(encoding="utf-8")
        assert "logger.exception" not in source
        assert "exc_info" not in source
        assert "response.text" not in source
        assert "response.content" not in source
        assert "str(exc)" not in source
        assert "repr(exc)" not in source


def test_domain_and_application_do_not_import_gmail() -> None:
    """Domain may name the mailbox provider slug; it must not import the adapter."""
    adapter_markers = (
        "infrastructure.connectors.gmail",
        "infrastructure.executors.gmail",
        "GmailCommunicationConnector",
        "GmailCommunicationActionExecutor",
        "gmail.googleapis.com",
        *_FORBIDDEN_SDK,
    )
    for root in (_DOMAIN_ROOT, _APPLICATION_ROOT):
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            for marker in adapter_markers:
                assert marker not in source, f"{path} must stay Gmail-adapter-agnostic"


def test_common_connector_helpers_do_not_use_google_sdk() -> None:
    for path in _python_files(_COMMON_ROOT):
        source = path.read_text(encoding="utf-8").lower()
        for marker in _FORBIDDEN_SDK:
            assert marker.lower() not in source
        assert "gmail" not in source
