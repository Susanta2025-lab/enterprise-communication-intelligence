"""Phase 20C BusinessContext communication provenance associations.

Revision ID: 20c0001
Revises: 20b0001
Create Date: 2026-09-18

Adds business_context_communication_links for many-to-many provenance
between user-owned BusinessContexts and provider-backed mailbox messages.
Does not create a communications table, attachment-link table, analysis
or workflow foreign keys, tenancy columns, or hierarchy.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20c0001"
down_revision: str | None = "20b0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_context_communication_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_context_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("connector_account_id", sa.Uuid(), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("associated_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("associated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("association_source", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "association_source IN ('manual')",
            name="ck_business_context_communication_links_association_source",
        ),
        sa.CheckConstraint(
            "length(trim(provider_message_id)) > 0",
            name="ck_business_context_communication_links_provider_message_id",
        ),
        sa.ForeignKeyConstraint(
            ["business_context_id"],
            ["business_contexts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_context_id",
            "connector_account_id",
            "provider_message_id",
            name="uq_bcc_links_context_connector_message",
        ),
    )
    op.create_index(
        "ix_bcc_links_context_associated_at_id",
        "business_context_communication_links",
        ["business_context_id", "associated_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_bcc_links_user_connector_message",
        "business_context_communication_links",
        ["user_id", "connector_account_id", "provider_message_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bcc_links_user_connector_message",
        table_name="business_context_communication_links",
    )
    op.drop_index(
        "ix_bcc_links_context_associated_at_id",
        table_name="business_context_communication_links",
    )
    op.drop_table("business_context_communication_links")
