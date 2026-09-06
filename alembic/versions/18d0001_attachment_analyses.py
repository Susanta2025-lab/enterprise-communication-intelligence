"""Phase 18D user-owned attachment analysis history.

Revision ID: 18d0001
Revises: 16f0001
Create Date: 2026-09-06

Adds attachment_analyses for structured attachment-analysis results only.
Does not store raw bytes, extracted document text, image bytes, prompts,
tokens, or credentials. Does not add a workflow_actions foreign key.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "18d0001"
down_revision: str | None = "16f0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PORTABLE_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "attachment_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connector_account_id", sa.Uuid(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("provider_attachment_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("extracted_content_status", sa.Text(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("warnings", _PORTABLE_JSON, nullable=False),
        sa.Column("reported_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("character_count", sa.Integer(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("summary_confidence", sa.Float(), nullable=True),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("action_items", _PORTABLE_JSON, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('pdf', 'docx', 'jpeg', 'png', 'txt')",
            name="ck_attachment_analyses_kind",
        ),
        sa.CheckConstraint(
            "extracted_content_status IN ('text', 'truncated_text', 'image')",
            name="ck_attachment_analyses_extracted_content_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attachment_analyses_user_id_created_at_id",
        "attachment_analyses",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_attachment_analyses_user_connector_message",
        "attachment_analyses",
        ["user_id", "connector_account_id", "provider_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attachment_analyses_user_connector_message",
        table_name="attachment_analyses",
    )
    op.drop_index(
        "ix_attachment_analyses_user_id_created_at_id",
        table_name="attachment_analyses",
    )
    op.drop_table("attachment_analyses")
