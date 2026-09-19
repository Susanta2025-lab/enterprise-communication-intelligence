"""SQLite round-trip tests for Alembic revision 20b0001."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.unit.infrastructure.storage.test_phase13a_migration import _create_phase12_schema

_ROOT = Path(__file__).resolve().parents[4]
_MIGRATION = _ROOT / "alembic" / "versions" / "20b0001_business_contexts.py"


def _config() -> Config:
    return Config(str(_ROOT / "alembic.ini"))


def test_20b_migration_source_has_expected_schema() -> None:
    """Revision 20b0001 creates business_contexts only."""
    migration = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "20b0001"' in migration
    assert 'down_revision: str | None = "19b0001"' in migration
    assert 'op.create_table(\n        "business_contexts"' in migration
    assert "ck_business_contexts_type" in migration
    assert "ck_business_contexts_status" in migration
    assert "ck_business_contexts_status_archived_at" in migration
    assert "ix_business_contexts_user_id_created_at_id" in migration
    assert "ix_business_contexts_user_id_status_updated_at" in migration
    assert 'ondelete="CASCADE"' in migration
    assert "business_context_communication_links" not in migration
    assert "parent_context_id" not in migration
    assert "organization_id" not in migration
    assert "tenant_id" not in migration
    assert "access_token" not in migration
    assert "clio_matter_id" not in migration


def test_upgrade_downgrade_reupgrade_from_19b0001(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """20b0001 must upgrade from 19b0001, downgrade, and re-upgrade without backfill."""
    db_path = tmp_path / "eci20b.db"
    sqlite_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    _create_phase12_schema(engine)
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: sqlite_url,
    )
    config = _config()
    command.upgrade(config, "19b0001")
    engine.dispose()

    engine = create_engine(sqlite_url)
    user_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, application_role, created_at, updated_at) "
                "VALUES (:id, 'user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": user_id},
        )
        assert "business_contexts" not in inspect(connection).get_table_names()
    engine.dispose()

    command.upgrade(config, "20b0001")
    engine = create_engine(sqlite_url)
    inspector = inspect(engine)
    assert "business_contexts" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("business_contexts")}
    assert columns == {
        "id",
        "user_id",
        "type",
        "title",
        "description",
        "reference",
        "status",
        "archived_at",
        "created_at",
        "updated_at",
    }
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "20b0001"
        count = connection.execute(text("SELECT COUNT(*) FROM business_contexts")).scalar()
        assert count == 0
        remaining = connection.execute(
            text("SELECT id FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar()
        assert remaining == user_id
        for table in (
            "users",
            "connector_accounts",
            "mailbox_authorization_sessions",
            "attachment_analyses",
            "business_contexts",
        ):
            assert table in inspector.get_table_names()
        assert "business_context_communication_links" not in inspector.get_table_names()
        assert "tenants" not in inspector.get_table_names()
        assert "messages" not in inspector.get_table_names()
    engine.dispose()

    command.downgrade(config, "19b0001")
    engine = create_engine(sqlite_url)
    inspector = inspect(engine)
    assert "business_contexts" not in inspector.get_table_names()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "19b0001"
        remaining_users = connection.execute(text("SELECT id FROM users")).all()
        assert [row.id for row in remaining_users] == [user_id]
    engine.dispose()

    command.upgrade(config, "20b0001")
    engine = create_engine(sqlite_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "20b0001"
        count = connection.execute(text("SELECT COUNT(*) FROM business_contexts")).scalar()
        assert count == 0
    engine.dispose()
