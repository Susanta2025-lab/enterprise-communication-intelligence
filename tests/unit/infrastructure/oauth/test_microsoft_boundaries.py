"""Architecture boundary tests for Phase 13D Microsoft OAuth."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_DOMAIN = _ROOT / "app" / "domain"
_APPLICATION = _ROOT / "app" / "application"
_CONNECTORS = _ROOT / "app" / "infrastructure" / "connectors"
_EXECUTORS = _ROOT / "app" / "infrastructure" / "executors"
_OAUTH = _ROOT / "app" / "infrastructure" / "oauth"
_FORBIDDEN_SDK = (
    "googleapiclient",
    "google-api-python-client",
    "msal",
    "azure.keyvault",
    "secretsmanager",
    "msgraph",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_domain_and_application_do_not_import_microsoft_oauth_http() -> None:
    for root in (_DOMAIN, _APPLICATION):
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert "login.microsoftonline.com" not in source
            assert "from msal" not in source
            assert "import msal" not in source
            for marker in _FORBIDDEN_SDK:
                assert marker not in source, f"{path} must not reference {marker}"


def test_graph_connectors_and_executors_remain_oauth_unaware() -> None:
    for path in (
        _CONNECTORS / "microsoft_graph" / "connector.py",
        _EXECUTORS / "microsoft_graph.py",
    ):
        source = path.read_text(encoding="utf-8").lower()
        assert "authorization_code" not in source
        assert "refresh_token" not in source
        assert "msal" not in source
        assert "mailboxoauth" not in source.replace("_", "")
        assert "pkce" not in source
        assert "login.microsoftonline.com" not in source


def test_microsoft_http_stays_inside_oauth_adapter() -> None:
    microsoft_mod = (_OAUTH / "microsoft.py").read_text(encoding="utf-8")
    assert "login.microsoftonline.com" in microsoft_mod
    assert "httpx" in microsoft_mod
    assert "import msal" not in microsoft_mod
    assert "from msal" not in microsoft_mod
    runtime = (_OAUTH / "runtime.py").read_text(encoding="utf-8")
    assert "InMemoryCommunicationCredentialStore" in runtime
    assert "production" in runtime.lower()
    assert "MicrosoftRefreshableCredentialAdapter" in runtime
    for path in _python_files(_OAUTH):
        source = path.read_text(encoding="utf-8")
        assert "import msal" not in source
        assert "from msal" not in source
        assert "azure.keyvault" not in source
        assert "msgraph" not in source


def test_gmail_adapter_does_not_gain_microsoft_urls() -> None:
    google_mod = (_OAUTH / "google.py").read_text(encoding="utf-8").lower()
    assert "login.microsoftonline.com" not in google_mod
    assert "msal" not in google_mod
