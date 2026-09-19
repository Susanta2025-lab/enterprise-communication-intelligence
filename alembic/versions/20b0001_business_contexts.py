"""Phase 20B user-owned BusinessContext foundation.

Revision ID: 20b0001
Revises: 19b0001
Create Date: 2026-09-18

Adds business_contexts for durable flat organizational contexts.
Does not add communication provenance links, attachment associations,
analysis/workflow foreign keys, tenancy columns, or hierarchy.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20b0001"
down_revision: str | None = "19b0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ("
            "'matter', 'case', 'project', 'client', 'transaction', 'account', 'other'"
            ")",
            name="ck_business_contexts_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_business_contexts_status",
        ),
        sa.CheckConstraint(
            "(status = 'active' AND archived_at IS NULL) OR "
            "(status = 'archived' AND archived_at IS NOT NULL)",
            name="ck_business_contexts_status_archived_at",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_business_contexts_user_id_created_at_id",
        "business_contexts",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_business_contexts_user_id_status_updated_at",
        "business_contexts",
        ["user_id", "status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_business_contexts_user_id_status_updated_at",
        table_name="business_contexts",
    )
    op.drop_index(
        "ix_business_contexts_user_id_created_at_id",
        table_name="business_contexts",
    )
    op.drop_table("business_contexts")
