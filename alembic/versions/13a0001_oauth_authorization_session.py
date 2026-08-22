"""Phase 13A mailbox authorization session and connector-account security foundation.

Revision ID: 13a0001
Revises: 12a0001
Create Date: 2026-08-22

Adds mailbox_authorization_sessions, ConnectorAccount REAUTH_REQUIRED, and
nullable granted_capabilities. Does not add credential_ref uniqueness or
OAuth token columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "13a0001"
down_revision: str | None = "12a0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PORTABLE_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("connector_accounts") as batch_op:
        batch_op.drop_constraint("ck_connector_accounts_status", type_="check")
        batch_op.create_check_constraint(
            "ck_connector_accounts_status",
            "status IN ('active', 'disconnected', 'reauth_required')",
        )
        batch_op.add_column(
            sa.Column("granted_capabilities", _PORTABLE_JSON, nullable=True),
        )

    op.create_table(
        "mailbox_authorization_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("connector_account_id", sa.Uuid(), nullable=True),
        sa.Column("state_hash", sa.Text(), nullable=False),
        sa.Column("pkce_verifier", sa.Text(), nullable=True),
        sa.Column("requested_capabilities", _PORTABLE_JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "provider IN ('gmail', 'microsoft_graph')",
            name="ck_mailbox_authorization_sessions_provider",
        ),
        sa.CheckConstraint(
            "purpose IN ('connect', 'reauthorize')",
            name="ck_mailbox_authorization_sessions_purpose",
        ),
        sa.CheckConstraint(
            "(purpose = 'connect' AND connector_account_id IS NULL) OR "
            "(purpose = 'reauthorize' AND connector_account_id IS NOT NULL)",
            name="ck_mailbox_authorization_sessions_purpose_account",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["connector_account_id"],
            ["connector_accounts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "state_hash",
            name="uq_mailbox_authorization_sessions_state_hash",
        ),
    )
    op.create_index(
        "ix_mailbox_authorization_sessions_expires_at",
        "mailbox_authorization_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_mailbox_authorization_sessions_user_id_created_at",
        "mailbox_authorization_sessions",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mailbox_authorization_sessions_user_id_created_at",
        table_name="mailbox_authorization_sessions",
    )
    op.drop_index(
        "ix_mailbox_authorization_sessions_expires_at",
        table_name="mailbox_authorization_sessions",
    )
    op.drop_table("mailbox_authorization_sessions")
    op.execute(
        sa.text(
            "UPDATE connector_accounts SET status = 'disconnected' "
            "WHERE status = 'reauth_required'"
        )
    )
    with op.batch_alter_table("connector_accounts") as batch_op:
        batch_op.drop_column("granted_capabilities")
        batch_op.drop_constraint("ck_connector_accounts_status", type_="check")
        batch_op.create_check_constraint(
            "ck_connector_accounts_status",
            "status IN ('active', 'disconnected')",
        )
