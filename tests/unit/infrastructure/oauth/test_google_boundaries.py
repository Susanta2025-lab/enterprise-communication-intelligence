"""Architecture boundary tests for Phase 13C Google OAuth."""

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
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_domain_and_application_do_not_import_google_sdk() -> None:
    for root in (_DOMAIN, _APPLICATION):
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert "from google.auth" not in source
            assert "import google.auth" not in source
            assert "google_auth_oauthlib" not in source
            assert "gmail.googleapis.com" not in source
            for marker in _FORBIDDEN_SDK:
                assert marker not in source, f"{path} must not reference {marker}"


def test_gmail_connectors_and_executors_remain_oauth_unaware() -> None:
    for path in (
        _CONNECTORS / "gmail" / "connector.py",
        _EXECUTORS / "gmail.py",
    ):
        source = path.read_text(encoding="utf-8").lower()
        assert "authorization_code" not in source
        assert "refresh_token" not in source
        assert "google_auth_oauthlib" not in source
        assert "mailboxoauth" not in source.replace("_", "")
        assert "pkce" not in source


def test_google_sdk_stays_inside_oauth_adapter() -> None:
    google_mod = (_OAUTH / "google.py").read_text(encoding="utf-8")
    assert "google_auth_oauthlib" in google_mod
    assert "google.oauth2" in google_mod
    assert "google-api-python-client" not in google_mod
    assert "googleapiclient" not in google_mod
    runtime = (_OAUTH / "runtime.py").read_text(encoding="utf-8")
    assert "InMemoryCommunicationCredentialStore" in runtime
    assert "production" in runtime.lower()
    for path in _python_files(_OAUTH):
        source = path.read_text(encoding="utf-8")
        assert "googleapiclient" not in source
        assert "msal" not in source
        assert "azure.keyvault" not in source


def test_no_microsoft_oauth_adapter() -> None:
    names = {path.name for path in _python_files(_OAUTH)}
    assert "google.py" in names
    assert "microsoft.py" not in names
    assert "msal.py" not in names
    for path in _python_files(_OAUTH):
        source = path.read_text(encoding="utf-8").lower()
        assert "login.microsoftonline.com" not in source
        assert "msal" not in source
