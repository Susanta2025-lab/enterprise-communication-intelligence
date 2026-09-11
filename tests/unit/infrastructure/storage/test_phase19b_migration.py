"""SQLite round-trip tests for Alembic revision 19b0001."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from tests.unit.infrastructure.storage.test_phase13a_migration import _create_phase12_schema

_ROOT = Path(__file__).resolve().parents[4]
_MIGRATION = _ROOT / "alembic" / "versions" / "19b0001_users_application_role.py"


def _config() -> Config:
    return Config(str(_ROOT / "alembic.ini"))


def test_19b_migration_source_has_expected_schema() -> None:
    """Revision 19b0001 adds constrained application_role only."""
    migration = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "19b0001"' in migration
    assert 'down_revision: str | None = "18d0001"' in migration
    assert "application_role" in migration
    assert "ck_users_application_role" in migration
    assert "application_role IN ('user', 'owner')" in migration
    assert 'server_default="user"' in migration
    assert "PLATFORM_OWNER" not in migration
    assert "email" not in migration
    assert "access_token" not in migration


def test_upgrade_defaults_existing_users_and_downgrade_preserves_ids(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing users become user; downgrade drops the column and keeps ids."""
    db_path = tmp_path / "eci19b.db"
    sqlite_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    _create_phase12_schema(engine)
    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: sqlite_url,
    )
    config = _config()
    command.upgrade(config, "18d0001")
    engine.dispose()

    engine = create_engine(sqlite_url)
    user_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, created_at, updated_at) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": user_id},
        )
        columns = {
            column["name"] for column in inspect(connection).get_columns("users")
        }
        assert "application_role" not in columns
    engine.dispose()

    command.upgrade(config, "19b0001")
    engine = create_engine(sqlite_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "19b0001"
        role = connection.execute(
            text("SELECT application_role FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar()
        assert role == "user"
        remaining = connection.execute(
            text("SELECT id FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar()
        assert remaining == user_id

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO users (id, application_role, created_at, updated_at) "
                    "VALUES (:id, 'admin', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": uuid4().hex},
            )
    engine.dispose()

    command.downgrade(config, "18d0001")
    engine = create_engine(sqlite_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "18d0001"
        columns = {
            column["name"] for column in inspect(connection).get_columns("users")
        }
        assert "application_role" not in columns
        remaining_users = connection.execute(text("SELECT id FROM users")).all()
        assert [row.id for row in remaining_users] == [user_id]
    engine.dispose()

    command.upgrade(config, "19b0001")
    engine = create_engine(sqlite_url)
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "19b0001"
        role = connection.execute(
            text("SELECT application_role FROM users WHERE id = :id"),
            {"id": user_id},
        ).scalar()
        assert role == "user"
    engine.dispose()
