"""Offline Alembic configuration tests. Do not connect to PostgreSQL."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.infrastructure.storage.models import Base

_ROOT = Path(__file__).resolve().parents[4]
_REQUIRED_TABLES = {"users", "external_identities", "analyses"}
_FORBIDDEN_TABLES = {
    "messages",
    "connections",
    "sync_state",
    "oauth_tokens",
    "workflows",
    "jobs",
    "tenants",
    "organizations",
    "memberships",
}


def test_alembic_revision_graph_is_valid() -> None:
    """The initial revision should be a single head with no down revision."""
    config = Config(str(_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())
    assert len(revisions) == 1
    revision = revisions[0]
    assert revision.revision == "9a0001"
    assert revision.down_revision is None
    assert script.get_current_head() == "9a0001"


def test_alembic_env_uses_base_metadata() -> None:
    """env.py must target the ORM metadata without running migrations."""
    env_source = (_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "target_metadata = Base.metadata" in env_source
    assert "from app.infrastructure.storage.models import Base" in env_source
    assert "get_settings().database_url" in env_source


def test_target_metadata_contains_phase9a_tables() -> None:
    """ORM metadata used by Alembic must include only the foundation tables."""
    table_names = set(Base.metadata.tables)
    assert _REQUIRED_TABLES <= table_names
    assert table_names.isdisjoint(_FORBIDDEN_TABLES)


def test_initial_migration_creates_expected_tables_and_constraints() -> None:
    """The hand-written migration should create the three tables and uniqueness."""
    migration = (
        _ROOT / "alembic" / "versions" / "9a0001_persistence_foundation.py"
    ).read_text(encoding="utf-8")
    assert 'op.create_table(\n        "users"' in migration
    assert 'op.create_table(\n        "external_identities"' in migration
    assert 'op.create_table(\n        "analyses"' in migration
    assert 'name="uq_external_identities_issuer_subject"' in migration
    assert 'ondelete="CASCADE"' in migration
    assert "postgresql.JSONB" in migration
    assert "op.drop_table(\"analyses\")" in migration
    assert "op.drop_table(\"external_identities\")" in migration
    assert "op.drop_table(\"users\")" in migration
    for forbidden in _FORBIDDEN_TABLES:
        assert f'"{forbidden}"' not in migration
    assert "raw_body" not in migration
    assert "access_token" not in migration
    assert "email" not in migration
