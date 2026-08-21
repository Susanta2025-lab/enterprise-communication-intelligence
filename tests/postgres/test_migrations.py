"""PostgreSQL migration and schema verification against a real database."""

from uuid import UUID

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from tests.postgres.alembic_checks import (
    ALLOWED_TABLES,
    APPLICATION_TABLES,
    current_and_head_revisions,
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


def test_alembic_current_revision_matches_head(postgres_test_url: str) -> None:
    """After upgrade, current must equal the Alembic script head."""
    current, head = current_and_head_revisions(postgres_test_url)
    assert current == head
    assert current is not None
    assert head is not None


def test_expected_tables_only(postgres_engine: Engine) -> None:
    """Application tables plus alembic_version should be the only public tables."""
    tables = set(inspect(postgres_engine).get_table_names())
    assert APPLICATION_TABLES <= tables
    assert tables <= ALLOWED_TABLES


def test_primary_keys(postgres_engine: Engine) -> None:
    """Each application table has a UUID primary key on id."""
    inspector = inspect(postgres_engine)
    for table in (
        "users",
        "external_identities",
        "analyses",
        "connector_accounts",
        "workflow_actions",
    ):
        pk = inspector.get_pk_constraint(table)
        assert pk["constrained_columns"] == ["id"]


def test_foreign_keys_cascade_to_users(postgres_engine: Engine) -> None:
    """Identity, analysis, connector, and workflow rows must reference users with CASCADE."""
    inspector = inspect(postgres_engine)
    identity_fks = inspector.get_foreign_keys("external_identities")
    analysis_fks = inspector.get_foreign_keys("analyses")
    connector_fks = inspector.get_foreign_keys("connector_accounts")
    workflow_fks = inspector.get_foreign_keys("workflow_actions")
    identity_ok = any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in identity_fks
    )
    analysis_ok = any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in analysis_fks
    )
    connector_ok = any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in connector_fks
    )
    workflow_ok = any(
        fk["referred_table"] == "users"
        and fk["constrained_columns"] == ["user_id"]
        and str((fk.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for fk in workflow_fks
    )
    assert identity_ok
    assert analysis_ok
    assert connector_ok
    assert workflow_ok
    assert all(fk["referred_table"] != "analyses" for fk in workflow_fks)


def test_external_identity_unique_constraint_named(postgres_engine: Engine) -> None:
    """issuer + subject uniqueness must use the named unique constraint."""
    inspector = inspect(postgres_engine)
    uniques = inspector.get_unique_constraints("external_identities")
    matching = [
        constraint
        for constraint in uniques
        if tuple(constraint["column_names"]) == ("issuer", "subject")
    ]
    assert matching
    assert matching[0]["name"] == "uq_external_identities_issuer_subject"


def test_expected_indexes(postgres_engine: Engine) -> None:
    """user_id lookup indexes exist on identity and analysis tables."""
    inspector = inspect(postgres_engine)
    identity_indexes = {index["name"] for index in inspector.get_indexes("external_identities")}
    analysis_indexes = {index["name"] for index in inspector.get_indexes("analyses")}
    workflow_indexes = {index["name"] for index in inspector.get_indexes("workflow_actions")}
    assert "ix_external_identities_user_id" in identity_indexes
    assert "ix_analyses_user_id" in analysis_indexes
    assert "ix_workflow_actions_user_id_created_at_id" in workflow_indexes


def test_nullability(postgres_engine: Engine) -> None:
    """Nullable columns match the Phase 9A schema."""
    inspector = inspect(postgres_engine)
    users = {column["name"]: column["nullable"] for column in inspector.get_columns("users")}
    identities = {
        column["name"]: column["nullable"]
        for column in inspector.get_columns("external_identities")
    }
    analyses = {
        column["name"]: column["nullable"] for column in inspector.get_columns("analyses")
    }
    assert users["id"] is False
    assert users["created_at"] is False
    assert users["updated_at"] is False
    assert identities["issuer"] is False
    assert identities["subject"] is False
    assert identities["user_id"] is False
    assert analyses["user_id"] is False
    assert analyses["summary_text"] is False
    assert analyses["action_items"] is False
    assert analyses["request_id"] is True
    assert analyses["message_id"] is True
    assert analyses["summary_confidence"] is True
    assert analyses["draft_reply"] is True


def test_uuid_column_types(postgres_engine: Engine) -> None:
    """UUID columns are real PostgreSQL uuid types."""
    types = _udt_types(
        postgres_engine,
        {
            ("users", "id"),
            ("external_identities", "id"),
            ("external_identities", "user_id"),
            ("analyses", "id"),
            ("analyses", "user_id"),
            ("analyses", "request_id"),
        },
    )
    assert set(types.values()) == {"uuid"}


def test_jsonb_column_types(postgres_engine: Engine) -> None:
    """action_items and draft_reply are JSONB on PostgreSQL."""
    types = _udt_types(
        postgres_engine,
        {("analyses", "action_items"), ("analyses", "draft_reply")},
    )
    assert types[("analyses", "action_items")] == "jsonb"
    assert types[("analyses", "draft_reply")] == "jsonb"


def test_timestamp_columns_are_timestamptz(postgres_engine: Engine) -> None:
    """Timestamp columns are timestamp with time zone."""
    types = _udt_types(
        postgres_engine,
        {
            ("users", "created_at"),
            ("users", "updated_at"),
            ("external_identities", "created_at"),
            ("analyses", "created_at"),
            ("analyses", "updated_at"),
        },
    )
    assert set(types.values()) == {"timestamptz"}


def test_schema_excludes_sensitive_columns(postgres_engine: Engine) -> None:
    """Persisted tables must not include message bodies, tokens, or email."""
    inspector = inspect(postgres_engine)
    for table in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns(table)}
        assert columns.isdisjoint(_FORBIDDEN_COLUMNS)
        if table == "workflow_actions":
            assert "proposed_reply_body" in columns
            assert "approved_reply_body" in columns
            assert "body" not in columns
            assert "raw_body" not in columns
        if table != "external_identities":
            assert "subject" not in columns
            assert "issuer" not in columns


def test_python_uuid_round_trip_types(postgres_engine: Engine) -> None:
    """Inspector UUID types correspond to SQLAlchemy Uuid columns used by repositories."""
    inspector = inspect(postgres_engine)
    users_id = next(
        column for column in inspector.get_columns("users") if column["name"] == "id"
    )
    python_type = getattr(users_id["type"], "python_type", None)
    assert python_type is UUID or str(users_id["type"]).lower().startswith("uuid")


def _udt_types(engine: Engine, columns: set[tuple[str, str]]) -> dict[tuple[str, str], str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name, column_name, udt_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND (table_name, column_name) IN (
                      ('users', 'id'),
                      ('users', 'created_at'),
                      ('users', 'updated_at'),
                      ('external_identities', 'id'),
                      ('external_identities', 'user_id'),
                      ('external_identities', 'created_at'),
                      ('analyses', 'id'),
                      ('analyses', 'user_id'),
                      ('analyses', 'request_id'),
                      ('analyses', 'created_at'),
                      ('analyses', 'updated_at'),
                      ('analyses', 'action_items'),
                      ('analyses', 'draft_reply')
                  )
                """
            )
        ).all()
    mapping = {(row.table_name, row.column_name): row.udt_name for row in rows}
    return {column: mapping[column] for column in columns}
