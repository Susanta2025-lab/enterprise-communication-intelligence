"""Offline Alembic configuration tests. Do not connect to PostgreSQL."""

import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.infrastructure.storage.models import Base

_ROOT = Path(__file__).resolve().parents[4]
_REQUIRED_TABLES = {
    "users",
    "external_identities",
    "analyses",
    "connector_accounts",
    "workflow_actions",
}
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
    "connector_credentials",
    "ingested_messages",
    "emails",
}


def test_alembic_revision_graph_is_valid() -> None:
    """Revisions must form a single linear history ending at the current head."""
    config = Config(str(_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    revisions = {revision.revision: revision for revision in script.walk_revisions()}
    assert set(revisions) == {"9a0001", "10b0001", "11b0001"}
    assert revisions["9a0001"].down_revision is None
    assert revisions["10b0001"].down_revision == "9a0001"
    assert revisions["11b0001"].down_revision == "10b0001"
    assert script.get_heads() == ["11b0001"]
    assert script.get_current_head() == "11b0001"


def test_alembic_env_uses_base_metadata() -> None:
    """env.py must target the ORM metadata without running migrations."""
    env_source = (_ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "target_metadata = Base.metadata" in env_source
    assert "from app.infrastructure.storage.models import Base" in env_source
    assert "resolve_migration_database_url" in env_source
    assert "get_settings" not in env_source
    assert "create_all" not in env_source
    assert "OIDC" not in env_source
    assert "fastapi" not in env_source.lower()


def test_target_metadata_contains_persistence_tables() -> None:
    """ORM metadata used by Alembic must include only the application tables."""
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


def test_offline_upgrade_sql_compiles_without_oidc_or_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """alembic upgrade head --sql must compile PostgreSQL SQL without connecting."""
    secret = "eci_offline_secret"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_AUDIENCE", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+psycopg://eci_offline:{secret}@127.0.0.1:5432/eci_offline",
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "CREATE TABLE" in sql
    assert "users" in sql
    assert "external_identities" in sql
    assert "analyses" in sql
    assert "JSONB" in sql or "jsonb" in sql
    assert "uq_external_identities_issuer_subject" in sql
    assert "CREATE TABLE connector_accounts" in sql
    assert "connector_accounts" in sql
    assert "uq_connector_accounts_user_provider_external_account" in sql
    assert "ck_connector_accounts_status" in sql
    assert "ix_connector_accounts_user_id_created_at_id" in sql
    assert "CREATE TABLE workflow_actions" in sql
    assert "workflow_actions" in sql
    assert "ck_workflow_actions_action_type" in sql
    assert "ck_workflow_actions_status" in sql
    assert "ix_workflow_actions_user_id_created_at_id" in sql
    assert "CREATE TABLE workflows" not in sql
    assert secret not in sql
    assert secret not in result.stderr


def test_connector_account_migration_creates_expected_schema() -> None:
    """The 10B migration must create connector_accounts without token columns."""
    migration = (
        _ROOT / "alembic" / "versions" / "10b0001_connector_accounts.py"
    ).read_text(encoding="utf-8")
    assert 'op.create_table(\n        "connector_accounts"' in migration
    assert 'name="uq_connector_accounts_user_provider_external_account"' in migration
    assert 'name="ck_connector_accounts_status"' in migration
    assert "ix_connector_accounts_user_id_created_at_id" in migration
    assert 'ondelete="CASCADE"' in migration
    assert "credential_ref" in migration
    assert 'op.drop_table("connector_accounts")' in migration
    assert "access_token" not in migration
    assert "refresh_token" not in migration
    assert "authorization_code" not in migration
    assert "client_secret" not in migration
    assert "gmail" not in migration.lower()
    assert "microsoft_graph" not in migration
    for forbidden in _FORBIDDEN_TABLES:
        assert f'"{forbidden}"' not in migration


def test_workflow_action_migration_creates_expected_schema() -> None:
    """The 11B migration must create workflow_actions without inbound mail columns."""
    migration = (
        _ROOT / "alembic" / "versions" / "11b0001_workflow_actions.py"
    ).read_text(encoding="utf-8")
    assert 'op.create_table(\n        "workflow_actions"' in migration
    assert 'name="ck_workflow_actions_action_type"' in migration
    assert 'name="ck_workflow_actions_status"' in migration
    assert "ix_workflow_actions_user_id_created_at_id" in migration
    assert 'ondelete="CASCADE"' in migration
    assert "proposed_reply_body" in migration
    assert "approved_reply_body" in migration
    assert 'op.drop_table("workflow_actions")' in migration
    assert "raw_body" not in migration
    assert "access_token" not in migration
    assert "refresh_token" not in migration
    assert '"sender"' not in migration
    assert '"recipient"' not in migration
    assert '"subject"' not in migration
    assert "credential_ref" not in migration
    for forbidden in _FORBIDDEN_TABLES:
        assert f'"{forbidden}"' not in migration


def test_alembic_head_check_uses_script_directory_not_database_revision() -> None:
    """Head must come from migration scripts; current must come from the database."""
    source = (_ROOT / "tests" / "postgres" / "alembic_checks.py").read_text(
        encoding="utf-8"
    )
    assert "script.get_current_head()" in source
    assert "context.get_current_revision()" in source
    assert "EXPECTED_HEAD" not in source


def test_assert_at_head_fails_when_database_is_one_revision_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database at 10b0001 must not pass when script head is 11b0001."""
    from tests.postgres import alembic_checks

    monkeypatch.setattr(
        alembic_checks,
        "current_and_head_revisions",
        lambda _url: ("10b0001", "11b0001"),
    )
    monkeypatch.setattr(
        alembic_checks,
        "application_tables",
        lambda _url: {
            "users",
            "external_identities",
            "analyses",
            "connector_accounts",
            "alembic_version",
        },
    )
    with pytest.raises(SystemExit, match="does not match head"):
        alembic_checks.assert_at_head("postgresql+psycopg://unused/unused")


def test_assert_at_head_passes_when_current_matches_script_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching current and script head with expected tables is success."""
    from tests.postgres import alembic_checks

    monkeypatch.setattr(
        alembic_checks,
        "current_and_head_revisions",
        lambda _url: ("11b0001", "11b0001"),
    )
    monkeypatch.setattr(
        alembic_checks,
        "application_tables",
        lambda _url: {
            "users",
            "external_identities",
            "analyses",
            "connector_accounts",
            "workflow_actions",
            "alembic_version",
        },
    )
    alembic_checks.assert_at_head("postgresql+psycopg://unused/unused")


def test_assert_at_head_fails_when_database_revision_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database at base must fail the head check."""
    from tests.postgres import alembic_checks

    monkeypatch.setattr(
        alembic_checks,
        "current_and_head_revisions",
        lambda _url: (None, "11b0001"),
    )
    with pytest.raises(SystemExit, match="does not match head"):
        alembic_checks.assert_at_head("postgresql+psycopg://unused/unused")


def test_assert_at_head_fails_when_script_head_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing script head (including failed single-head resolution) must fail."""
    from tests.postgres import alembic_checks

    monkeypatch.setattr(
        alembic_checks,
        "current_and_head_revisions",
        lambda _url: ("11b0001", None),
    )
    with pytest.raises(SystemExit, match="does not match head"):
        alembic_checks.assert_at_head("postgresql+psycopg://unused/unused")
