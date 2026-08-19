"""ORM schema tests for Phase 9A persistence models."""

from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.storage.models import Analysis, Base, ExternalIdentity, User

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
    }
)


def test_expected_tables_exist(sqlite_engine: Engine) -> None:
    """users, external_identities, and analyses must be present."""
    inspector = inspect(sqlite_engine)
    tables = set(inspector.get_table_names())
    assert {"users", "external_identities", "analyses"} <= tables
    assert "messages" not in tables
    assert "connections" not in tables
    assert "oauth_tokens" not in tables
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
    """Identity and analysis rows must reference users with ON DELETE CASCADE."""
    inspector = inspect(sqlite_engine)
    identity_fks = inspector.get_foreign_keys("external_identities")
    analysis_fks = inspector.get_foreign_keys("analyses")
    assert any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
        for fk in identity_fks
    )
    assert any(
        fk["referred_table"] == "users" and fk["constrained_columns"] == ["user_id"]
        for fk in analysis_fks
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
    """Declarative metadata should expose the three Phase 9A tables."""
    assert set(Base.metadata.tables) == {"users", "external_identities", "analyses"}
    assert User.__tablename__ == "users"
    assert ExternalIdentity.__tablename__ == "external_identities"
    assert Analysis.__tablename__ == "analyses"


def test_sqlite_foreign_keys_are_enabled(session_factory: sessionmaker) -> None:
    """SQLite tests must enforce foreign keys."""
    with session_factory() as session:
        enabled = session.execute(text("PRAGMA foreign_keys")).scalar()
    assert enabled == 1
