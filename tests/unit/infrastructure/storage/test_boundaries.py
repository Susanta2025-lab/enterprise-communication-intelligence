"""Architecture boundary tests for persistence placement."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_SQLALCHEMY_FREE_ROOTS = (
    _ROOT / "app" / "domain",
    _ROOT / "app" / "application",
    _ROOT / "app" / "api",
    _ROOT / "app" / "providers",
)
_NO_CREATE_ALL_ROOTS = (
    _ROOT / "app" / "main.py",
    _ROOT / "app" / "api",
    _ROOT / "app" / "application",
    _ROOT / "app" / "core",
    _ROOT / "app" / "infrastructure" / "storage" / "database.py",
    _ROOT / "app" / "infrastructure" / "storage" / "repositories",
)


def _python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(path for path in root.rglob("*.py") if path.name != "__pycache__")


def test_domain_application_api_and_providers_do_not_import_sqlalchemy() -> None:
    """SQLAlchemy belongs in infrastructure storage, Alembic, and tests."""
    for root in _SQLALCHEMY_FREE_ROOTS:
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert "sqlalchemy" not in source, f"{path} must not import SQLAlchemy"


def test_create_all_is_not_used_at_application_startup() -> None:
    """create_all is allowed only in isolated SQLite unit-test fixtures."""
    for root in _NO_CREATE_ALL_ROOTS:
        for path in _python_files(root):
            source = path.read_text(encoding="utf-8")
            assert "create_all" not in source, f"{path} must not call create_all"
