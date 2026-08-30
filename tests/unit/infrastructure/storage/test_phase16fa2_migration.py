"""SQLite round-trip tests for Alembic revision 16f0001."""

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


def test_downgrade_removes_connect_another_sessions_not_connector_rows(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Downgrade deletes ephemeral CONNECT_ANOTHER sessions only."""
    db_path = tmp_path / "eci16fa2.db"
    sqlite_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    _create_phase12_schema(engine)
    user_id = uuid4().hex
    account_id = uuid4().hex
    connect_id = uuid4().hex
    another_id = uuid4().hex
    reauthorize_id = uuid4().hex
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
                "INSERT INTO connector_accounts "
                "(id, user_id, provider, external_account_id, credential_ref, "
                "status, created_at, updated_at) VALUES "
                "(:id, :user_id, 'gmail', 'mailbox-a', 'demo-account', "
                "'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": account_id, "user_id": user_id},
        )

    monkeypatch.setattr(
        "app.infrastructure.storage.migration_config.resolve_migration_database_url",
        lambda: sqlite_url,
    )
    config = _config()
    command.upgrade(config, "16f0001")

    inspector = inspect(engine)
    connector_columns = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("connector_accounts")
    }
    assert connector_columns["display_identity"] is True

    with engine.begin() as connection:
        for session_id, purpose, bound in (
            (connect_id, "connect", None),
            (another_id, "connect_another", None),
            (reauthorize_id, "reauthorize", account_id),
        ):
            connection.execute(
                text(
                    "INSERT INTO mailbox_authorization_sessions "
                    "(id, user_id, provider, purpose, connector_account_id, "
                    "state_hash, pkce_verifier, requested_capabilities, "
                    "created_at, expires_at, consumed_at) VALUES "
                    "(:id, :user_id, 'gmail', :purpose, :bound, :state_hash, "
                    "'verifier', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, NULL)"
                ),
                {
                    "id": session_id,
                    "user_id": user_id,
                    "purpose": purpose,
                    "bound": bound,
                    "state_hash": f"hash-{purpose}",
                },
            )
        purposes_before = {
            row.purpose
            for row in connection.execute(
                text("SELECT purpose FROM mailbox_authorization_sessions")
            )
        }
        assert purposes_before == {"connect", "connect_another", "reauthorize"}

    command.downgrade(config, "13a0001")
    inspector = inspect(engine)
    connector_columns = {
        column["name"] for column in inspector.get_columns("connector_accounts")
    }
    assert "display_identity" not in connector_columns
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "13a0001"
        surviving_accounts = connection.execute(
            text("SELECT id, credential_ref, status FROM connector_accounts")
        ).all()
        assert len(surviving_accounts) == 1
        assert surviving_accounts[0].id == account_id
        assert surviving_accounts[0].credential_ref == "demo-account"
        assert surviving_accounts[0].status == "active"
        purposes = {
            row.purpose
            for row in connection.execute(
                text("SELECT purpose FROM mailbox_authorization_sessions")
            )
        }
        assert purposes == {"connect", "reauthorize"}
    engine.dispose()
