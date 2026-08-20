"""ORM schema tests for Phase 9A persistence models."""

from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.storage.models import (
    Analysis,
    Base,
    ConnectorAccount,
    ExternalIdentity,
    User,
)

_FORBIDDEN_COLUMNS = frozenset(
    {
        "raw_body",
        "body",
        "message_body",
        "email_body",
        "subject_line",
        "sender",
        "recipients",
        "attachments",
        "email",
        "display_name",
        "name",
        "password",
        "access_token",
        "refresh_token",
        "jwt",
        "authorization_header",
        "token",
        "authorization_code",
        "client_secret",
    }
)


def test_expected_tables_exist(sqlite_engine: Engine) -> None:
    """users, external_identities, analyses, and connector_accounts must be present."""
    inspector = inspect(sqlite_engine)
    tables = set(inspector.get_table_names())
    assert {"users", "external_identities", "analyses", "connector_accounts"} <= tables
    assert "messages" not in tables
    assert "connections" not in tables
    assert "oauth_tokens" not in tables
    assert "connector_credentials" not in tables
    assert "tenants" not in tables


def test_user_columns_exclude_pii(sqlite_engine: Engine) -> None:
    """User rows are an opaque UUID plus timestamps."""
    inspector = inspect(sqlite_engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    assert columns == {"id", "created_at", "updated_at"}
    assert columns.isdisjoint(_FORBIDDEN_COLUMNS)


def test_external_identity_unique_constraint(sqlite_engine: Engine) -> None:
    """issuer + subject must be unique."""
    inspector = inspect(sqlite_engine)
    uniques = inspector.get_unique_constraints("external_identities")
    column_sets = {tuple(constraint["column_names"]) for constraint in uniques}
    indexes = inspector.get_indexes("external_identities")
    unique_indexes = {
        tuple(index["column_names"]) for index in indexes if index.get("unique")
    }
    assert ("issuer", "subject") in column_sets or ("issuer", "subject") in unique_indexes


def test_foreign_keys_cascade_to_users(sqlite_engine: Engine) -> None:
    """Identity, analysis, and connector account rows must reference users with CASCADE."""
    inspector = inspect(sqlite_engine)
    identity_fks = inspector.get_foreign_keys("external_identities")
    analysis_fks = inspector.get_foreign_keys("analyses")
    connector_fks = inspector.get_foreign_keys("connector_accounts")
    assert any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
        for fk in identity_fks
    )
    assert any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
        for fk in analysis_fks
    )
    assert any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
        for fk in connector_fks
    )


def test_analysis_columns_are_minimized(sqlite_engine: Engine) -> None:
    """Analysis storage must not include raw communication or credential fields."""
    inspector = inspect(sqlite_engine)
    columns = {column["name"] for column in inspector.get_columns("analyses")}
    expected = {
        "id",
        "user_id",
        "created_at",
        "updated_at",
        "request_id",
        "provider",
        "priority",
        "category",
        "source_type",
        "message_id",
        "summary_text",
        "summary_confidence",
        "action_items",
        "draft_reply",
    }
    assert expected <= columns
    assert columns.isdisjoint(_FORBIDDEN_COLUMNS)
    assert "subject" not in columns
    assert "connector_account_id" not in columns


def test_subject_exists_only_on_external_identities(sqlite_engine: Engine) -> None:
    """The OIDC subject column belongs only to external_identities."""
    inspector = inspect(sqlite_engine)
    for table in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns(table)}
        if table == "external_identities":
            assert "subject" in columns
            assert "issuer" in columns
        else:
            assert "subject" not in columns


def test_orm_metadata_matches_mapped_classes() -> None:
    """Declarative metadata should expose the persistence tables."""
    assert set(Base.metadata.tables) == {
        "users",
        "external_identities",
        "analyses",
        "connector_accounts",
    }
    assert User.__tablename__ == "users"
    assert ExternalIdentity.__tablename__ == "external_identities"
    assert Analysis.__tablename__ == "analyses"
    assert ConnectorAccount.__tablename__ == "connector_accounts"


def test_connector_account_columns_are_minimized(sqlite_engine: Engine) -> None:
    """Connector accounts store an opaque locator, not credential material."""
    inspector = inspect(sqlite_engine)
    columns = {column["name"] for column in inspector.get_columns("connector_accounts")}
    assert columns == {
        "id",
        "user_id",
        "provider",
        "external_account_id",
        "credential_ref",
        "status",
        "created_at",
        "updated_at",
    }
    assert columns.isdisjoint(_FORBIDDEN_COLUMNS)
    assert "email" not in columns
    assert "display_name" not in columns
    assert "mailbox_address" not in columns


def test_connector_account_unique_constraint(sqlite_engine: Engine) -> None:
    """Owner + provider + external account id must be unique."""
    inspector = inspect(sqlite_engine)
    uniques = inspector.get_unique_constraints("connector_accounts")
    expected = ("user_id", "provider", "external_account_id")
    named = [
        constraint
        for constraint in uniques
        if tuple(constraint["column_names"]) == expected
    ]
    indexes = inspector.get_indexes("connector_accounts")
    unique_indexes = {
        tuple(index["column_names"]) for index in indexes if index.get("unique")
    }
    assert named or expected in unique_indexes
    if named:
        assert named[0]["name"] == "uq_connector_accounts_user_provider_external_account"


def test_schema_excludes_token_columns(sqlite_engine: Engine) -> None:
    """No table may persist token or secret columns. credential_ref is not a token."""
    inspector = inspect(sqlite_engine)
    forbidden = {
        "access_token",
        "refresh_token",
        "token",
        "authorization_code",
        "client_secret",
        "jwt",
    }
    for table in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert columns.isdisjoint(forbidden)
        if table == "connector_accounts":
            assert "credential_ref" in columns


def test_sqlite_foreign_keys_are_enabled(session_factory: sessionmaker) -> None:
    """SQLite tests must enforce foreign keys."""
    with session_factory() as session:
        enabled = session.execute(text("PRAGMA foreign_keys")).scalar()
    assert enabled == 1
