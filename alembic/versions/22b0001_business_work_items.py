"""Phase 22B additive tracking aggregate, sources and atomic journal.

Revision ID: 22b0001
Revises: 21d0001
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "22b0001"
down_revision: str = "21d0001"
branch_labels = None
depends_on = None


_SQL_WHITESPACE = (
    " \t\n\r\v\f\x1c\x1d\x1e\x1f\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000"
)


def _tracking_sql_check(sql: str) -> str:
    for field in ("title", "description", "provider_message_id", "provider_attachment_id"):
        sql = sql.replace(f"trim({field})", f"trim({field}, '{_SQL_WHITESPACE}')")
    return sql


def upgrade() -> None:
    op.create_table(
        "business_work_items",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("business_context_id", sa.Uuid(), nullable=True),
        sa.Column("due_kind", sa.Text(), nullable=False, server_default="none"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_timezone", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("creation_origin", sa.Text(), nullable=False),
        sa.Column("confirmed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creation_key", sa.Text(), nullable=False),
        sa.Column("creation_request_hash", sa.Text(), nullable=False),
        sa.Column("origin_candidate_key", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('action','obligation')", name="ck_bwi_kind"),
        sa.CheckConstraint(
            "status IN ('open','in_progress','completed','cancelled')", name="ck_bwi_status"
        ),
        sa.CheckConstraint(
            _tracking_sql_check("length(trim(title)) BETWEEN 1 AND 200 AND title = trim(title)"),
            name="ck_bwi_title",
        ),
        sa.CheckConstraint(
            _tracking_sql_check(
                "description IS NULL OR (length(trim(description)) BETWEEN 1 AND 4000 AND "
                "description = trim(description))"
            ),
            name="ck_bwi_description",
        ),
        sa.CheckConstraint(
            "(due_kind = 'none' AND due_date IS NULL AND due_at IS NULL AND due_timezone "
            "IS NULL) OR (due_kind = 'date' AND due_date IS NOT NULL AND due_at IS NULL "
            "AND due_timezone IS NOT NULL AND length(trim(due_timezone)) BETWEEN 1 AND "
            "64) OR (due_kind = 'datetime' AND due_date IS NULL AND due_at IS NOT NULL "
            "AND due_timezone IS NOT NULL AND length(trim(due_timezone)) BETWEEN 1 AND "
            "64)",
            name="ck_bwi_due",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND completed_at IS NOT NULL) OR (status <> "
            "'completed' AND completed_at IS NULL)",
            name="ck_bwi_completed",
        ),
        sa.CheckConstraint(
            "(status = 'cancelled' AND cancelled_at IS NOT NULL) OR (status <> "
            "'cancelled' AND cancelled_at IS NULL)",
            name="ck_bwi_cancelled",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at AND (completed_at IS NULL OR completed_at >= "
            "created_at) AND (cancelled_at IS NULL OR cancelled_at >= created_at) AND "
            "(archived_at IS NULL OR archived_at >= created_at)",
            name="ck_bwi_times",
        ),
        sa.CheckConstraint("version >= 1", name="ck_bwi_version"),
        sa.CheckConstraint(
            "(creation_origin = 'manual' AND confirmed_by_user_id IS NULL AND "
            "confirmed_at IS NULL AND origin_candidate_key IS NULL) OR (creation_origin "
            "= 'ai_confirmed' AND confirmed_by_user_id IS NOT NULL AND "
            "confirmed_by_user_id = user_id AND confirmed_at IS NOT NULL AND "
            "confirmed_at >= created_at AND origin_candidate_key IS NOT NULL)",
            name="ck_bwi_confirmation",
        ),
        sa.CheckConstraint(
            "length(creation_request_hash) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(creation_request_hash, "
            "'0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', "
            "''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), "
            "'f', '') = ''",
            name="ck_bwi_request_hash",
        ),
        sa.CheckConstraint(
            "origin_candidate_key IS NULL OR (length(origin_candidate_key) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(origin_candidate_key, "
            "'0', ''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', "
            "''), '8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), "
            "'f', '') = '')",
            name="ck_bwi_candidate_key",
        ),
        sa.CheckConstraint(
            "length(creation_key) BETWEEN 1 AND 128", name="ck_bwi_creation_key_length"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_bwi_id_user"),
        sa.UniqueConstraint("user_id", "creation_key", name="uq_bwi_creation"),
        sa.UniqueConstraint("user_id", "origin_candidate_key", name="uq_bwi_candidate"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["business_context_id"], ["business_contexts.id"], ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "creation_key NOT GLOB '*[^A-Za-z0-9._~-]*'"
            if op.get_bind().dialect.name == "sqlite"
            else "creation_key !~ '[^A-Za-z0-9._~-]'",
            name="ck_bwi_key_ascii_sqlite"
            if op.get_bind().dialect.name == "sqlite"
            else "ck_bwi_key_ascii_pg",
        ),
    )
    op.create_index("ix_bwi_owner_created", "business_work_items", ["user_id", "created_at", "id"])
    op.create_index(
        "ix_bwi_owner_status_at", "business_work_items", ["user_id", "status", "due_at", "id"]
    )
    op.create_index(
        "ix_bwi_owner_status_date", "business_work_items", ["user_id", "status", "due_date", "id"]
    )
    op.create_index(
        "ix_bwi_owner_context",
        "business_work_items",
        ["user_id", "business_context_id", "created_at", "id"],
    )
    op.create_table(
        "business_work_item_sources",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("attachment_analysis_id", sa.Uuid(), nullable=True),
        sa.Column("connector_account_id", sa.Uuid(), nullable=True),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("provider_attachment_id", sa.Text(), nullable=True),
        sa.Column("candidate_field", sa.Text(), nullable=True),
        sa.Column("candidate_index", sa.Integer(), nullable=True),
        sa.Column("candidate_digest", sa.Text(), nullable=True),
        sa.Column("source_key", sa.Text(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('communication','communication_analysis','attachment_analysis')",
            name="ck_bwis_kind",
        ),
        sa.CheckConstraint(
            "(connector_account_id IS NULL AND provider_message_id IS NULL) OR "
            "(connector_account_id IS NOT NULL AND provider_message_id IS NOT NULL)",
            name="ck_bwis_pair",
        ),
        sa.CheckConstraint(
            "(candidate_field IS NULL AND candidate_index IS NULL AND candidate_digest "
            "IS NULL) OR (candidate_field IS NOT NULL AND candidate_field IN "
            "('action_items','potential_action_mentions','potential_dates') AND "
            "candidate_index IS NOT NULL AND candidate_index >= 0 AND candidate_digest "
            "IS NOT NULL AND length(candidate_digest) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(candidate_digest, '0', "
            "''), '1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), "
            "'8', ''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', "
            "'') = '')",
            name="ck_bwis_locator",
        ),
        sa.CheckConstraint(
            "(source_kind = 'communication' AND connector_account_id IS NOT NULL AND "
            "provider_message_id IS NOT NULL AND analysis_id IS NULL AND "
            "attachment_analysis_id IS NULL AND provider_attachment_id IS NULL AND "
            "candidate_field IS NULL) OR (source_kind = 'communication_analysis' AND "
            "analysis_id IS NOT NULL AND attachment_analysis_id IS NULL AND "
            "provider_attachment_id IS NULL AND (candidate_field IS NULL OR "
            "candidate_field = 'action_items')) OR (source_kind = 'attachment_analysis' "
            "AND analysis_id IS NULL AND attachment_analysis_id IS NOT NULL AND "
            "connector_account_id IS NOT NULL AND provider_message_id IS NOT NULL AND "
            "provider_attachment_id IS NOT NULL)",
            name="ck_bwis_reference",
        ),
        sa.CheckConstraint(
            "length(source_key) = 64 AND "
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(repl"
            "ace(replace(replace(replace(replace(replace(replace(source_key, '0', ''), "
            "'1', ''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', "
            "''), '9', ''), 'a', ''), 'b', ''), 'c', ''), 'd', ''), 'e', ''), 'f', '') = "
            "''",
            name="ck_bwis_key",
        ),
        sa.CheckConstraint(
            _tracking_sql_check(
                "provider_message_id IS NULL OR (length(trim(provider_message_id)) >= 1 AND "
                "length(provider_message_id) <= 2048)"
            ),
            name="ck_bwis_provider_message_id",
        ),
        sa.CheckConstraint(
            _tracking_sql_check(
                "provider_attachment_id IS NULL OR (length(trim(provider_attachment_id)) >= "
                "1 AND length(provider_attachment_id) <= 2048)"
            ),
            name="ck_bwis_provider_attachment_id",
        ),
        sa.UniqueConstraint("work_item_id", "source_key", name="uq_bwis_source"),
        sa.ForeignKeyConstraint(
            ["work_item_id", "user_id"],
            ["business_work_items.id", "business_work_items.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "business_work_item_events",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_version", sa.Integer(), nullable=False),
        sa.Column("event_ordinal", sa.Integer(), nullable=False),
        sa.Column("context_at_event_id", sa.Uuid(), nullable=True),
        sa.Column(
            "metadata",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
            server_default="{}",
        ),
        sa.CheckConstraint(
            "event_type IN "
            "('created','edited','status_changed','archived','restored','context_associat"
            "ed','context_disassociated')",
            name="ck_bwie_type",
        ),
        sa.CheckConstraint("actor_user_id = user_id", name="ck_bwie_actor"),
        sa.CheckConstraint("item_version >= 1 AND event_ordinal >= 0", name="ck_bwie_version"),
        sa.UniqueConstraint("work_item_id", "item_version", "event_ordinal", name="uq_bwie_order"),
        sa.ForeignKeyConstraint(
            ["work_item_id", "user_id"],
            ["business_work_items.id", "business_work_items.user_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_bwie_owner_item",
        "business_work_item_events",
        ["user_id", "work_item_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_bwie_owner_context",
        "business_work_item_events",
        ["user_id", "context_at_event_id", "occurred_at", "id"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    tables = ("business_work_item_events", "business_work_item_sources", "business_work_items")
    # Prevent a concurrent insert between the population check and DROP on PostgreSQL.
    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text(
                "LOCK TABLE business_work_items, business_work_item_sources, "
                "business_work_item_events IN ACCESS EXCLUSIVE MODE"
            )
        )
    # Inspect ALL tables before ANY destructive DDL, even if the root is empty.
    populated = [
        connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() is not None
        for table in tables
    ]
    if any(populated):
        raise RuntimeError("Cannot downgrade 22b0001 while tracking data exists.")
    for table in tables:
        op.drop_table(table)
