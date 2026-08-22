"""SQLite round-trip tests for Alembic revision 13a0001."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

_ROOT = Path(__file__).resolve().parents[4]
_MIGRATION = _ROOT / "alembic" / "versions" / "13a0001_oauth_authorization_session.py"


def _config() -> Config:
    return Config(str(_ROOT / "alembic.ini"))


def _create_phase12_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE connector_accounts (
                    id CHAR(32) NOT NULL PRIMARY KEY,
                    user_id CHAR(32) NOT NULL,
                    provider TEXT NOT NULL,
                    external_account_id TEXT NOT NULL,
                    credential_ref TEXT,
                    status TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    CONSTRAINT ck_connector_accounts_status
                        CHECK (status IN ('active', 'disconnected'))
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
            )
        )
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('12a0001')"))


def test_13a_migration_source_has_expected_schema_and_omits_tokens() -> None:
    """Revision 13a0001 adds sessions and capabilities without token columns."""
    migration = _MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "13a0001"' in migration
    assert 'down_revision: str | None = "12a0001"' in migration
    assert "mailbox_authorization_sessions" in migration
    assert "granted_capabilities" in migration
    assert "reauth_required" in migration
    assert "ck_connector_accounts_status" in migration
    assert "uq_mailbox_authorization_sessions_state_hash" in migration
    assert "uq_connector_accounts_credential_ref" not in migration
    assert "access_token" not in migration
    assert "refresh_token" not in migration
    assert "authorization_code" not in migration
    assert "client_secret" not in migration
    assert 'op.create_index(\n        "credential_ref"' not in migration
    assert 'UniqueConstraint(\n            "credential_ref"' not in migration


def test_upgrade_from_12a0001_and_downgrade_preserve_connector_rows(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing accounts and duplicate credential_ref values survive 13A."""
    db_path = tmp_path / "eci13a.db"
    sqlite_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    _create_phase12_schema(engine)
    user_id = uuid4().hex
    first_id = uuid4().hex
    second_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, created_at, updated_at) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": user_id},
        )
        for account_id, external_id in ((first_id, "mailbox-a"), (second_id, "mailbox-b")):
            connection.execute(
                text(
                    "INSERT INTO connector_accounts "
                    "(id, user_id, provider, external_account_id, credential_ref, "
                    "status, created_at, updated_at) VALUES "
                    "(:id, :user_id, 'gmail', :external_id, 'demo-account', "
                    "'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"id": account_id, "user_id": user_id, "external_id": external_id},
            )

    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: sqlite_url,
    )
    config = _config()
    command.upgrade(config, "13a0001")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "mailbox_authorization_sessions" in tables
    connector_columns = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("connector_accounts")
    }
    assert connector_columns["granted_capabilities"] is True
    assert connector_columns["credential_ref"] is True
    uniques = inspector.get_unique_constraints("connector_accounts")
    unique_indexes = [
        index for index in inspector.get_indexes("connector_accounts") if index.get("unique")
    ]
    for constraint in uniques:
        assert "credential_ref" not in constraint["column_names"]
    for index in unique_indexes:
        assert "credential_ref" not in (index.get("column_names") or [])

    with engine.begin() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "13a0001"
        rows = connection.execute(
            text(
                "SELECT credential_ref, granted_capabilities, status "
                "FROM connector_accounts ORDER BY external_account_id"
            )
        ).all()
        assert len(rows) == 2
        assert {row.credential_ref for row in rows} == {"demo-account"}
        assert {row.granted_capabilities for row in rows} == {None}
        connection.execute(
            text(
                "UPDATE connector_accounts SET status = 'reauth_required' "
                "WHERE id = :id"
            ),
            {"id": first_id},
        )
        remaining = connection.execute(
            text("SELECT status FROM connector_accounts WHERE id = :id"),
            {"id": first_id},
        ).scalar()
        assert remaining == "reauth_required"

    command.downgrade(config, "12a0001")
    inspector = inspect(engine)
    assert "mailbox_authorization_sessions" not in set(inspector.get_table_names())
    columns = {column["name"] for column in inspector.get_columns("connector_accounts")}
    assert "granted_capabilities" not in columns
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "12a0001"
        surviving = connection.execute(
            text("SELECT id, credential_ref, status FROM connector_accounts")
        ).all()
        assert len(surviving) == 2
        assert {row.credential_ref for row in surviving} == {"demo-account"}
        statuses = {row.id: row.status for row in surviving}
        assert statuses[first_id] == "disconnected"
        assert statuses[second_id] == "active"
    engine.dispose()
