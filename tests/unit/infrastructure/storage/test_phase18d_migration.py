"""SQLite round-trip tests for Alembic revision 18d0001."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from tests.unit.infrastructure.storage.test_phase13a_migration import _create_phase12_schema

_ROOT = Path(__file__).resolve().parents[4]


def _config() -> Config:
    return Config(str(_ROOT / "alembic.ini"))


def test_upgrade_downgrade_reupgrade_from_16f0001(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """18d0001 must upgrade from 16f0001, downgrade, and re-upgrade."""
    db_path = tmp_path / "eci18d.db"
    sqlite_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    _create_phase12_schema(engine)
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: sqlite_url,
    )
    config = _config()
    command.upgrade(config, "16f0001")
    inspector = inspect(engine)
    assert "attachment_analyses" not in inspector.get_table_names()
    engine.dispose()

    command.upgrade(config, "18d0001")
    engine = create_engine(sqlite_url)
    inspector = inspect(engine)
    assert "attachment_analyses" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("attachment_analyses")}
    assert "summary_text" in columns
    assert "extracted_text" not in columns
    assert "content" not in columns
    assert "draft_reply" not in columns
    user_id = uuid4().hex
    analysis_id = uuid4().hex
    connector_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, created_at, updated_at) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO attachment_analyses ("
                "id, user_id, created_at, updated_at, connector_account_id, "
                "provider_message_id, provider_attachment_id, filename, media_type, "
                "kind, extracted_content_status, truncated, warnings, summary_text, "
                "priority, category, action_items, provider"
                ") VALUES ("
                ":id, :user_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :connector_id, "
                "'msg-1', 'att-1', 'notes.txt', 'text/plain', 'txt', 'text', 0, "
                "'[]', 'Structured summary', 'medium', 'general', '[]', 'mock')"
            ),
            {"id": analysis_id, "user_id": user_id, "connector_id": connector_id},
        )
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "18d0001"
    engine.dispose()

    command.downgrade(config, "16f0001")
    engine = create_engine(sqlite_url)
    inspector = inspect(engine)
    assert "attachment_analyses" not in inspector.get_table_names()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "16f0001"
        remaining_users = connection.execute(text("SELECT id FROM users")).all()
        assert [row.id for row in remaining_users] == [user_id]
    engine.dispose()

    command.upgrade(config, "18d0001")
    engine = create_engine(sqlite_url)
    inspector = inspect(engine)
    assert "attachment_analyses" in inspector.get_table_names()
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "18d0001"
        count = connection.execute(text("SELECT COUNT(*) FROM attachment_analyses")).scalar()
        assert count == 0
    engine.dispose()
