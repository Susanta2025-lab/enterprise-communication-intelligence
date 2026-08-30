"""Phase 16F-A2 safe display identity and connect-another purpose.

Revision ID: 16f0001
Revises: 13a0001
Create Date: 2026-08-30

Adds nullable presentation-only display_identity on connector_accounts and
CONNECT_ANOTHER as an unbound mailbox authorization purpose. Does not change
durable external_account_id uniqueness or reconnect matching. Downgrade
deletes ephemeral connect_another authorization sessions only; it does not
delete connector_accounts.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "16f0001"
down_revision: str | None = "13a0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("connector_accounts") as batch_op:
        batch_op.add_column(sa.Column("display_identity", sa.Text(), nullable=True))

    with op.batch_alter_table("mailbox_authorization_sessions") as batch_op:
        batch_op.drop_constraint(
            "ck_mailbox_authorization_sessions_purpose",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_mailbox_authorization_sessions_purpose_account",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_mailbox_authorization_sessions_purpose",
            "purpose IN ('connect', 'reauthorize', 'connect_another')",
        )
        batch_op.create_check_constraint(
            "ck_mailbox_authorization_sessions_purpose_account",
            "(purpose IN ('connect', 'connect_another') AND connector_account_id IS NULL) OR "
            "(purpose = 'reauthorize' AND connector_account_id IS NOT NULL)",
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM mailbox_authorization_sessions WHERE purpose = 'connect_another'"
        )
    )
    with op.batch_alter_table("mailbox_authorization_sessions") as batch_op:
        batch_op.drop_constraint(
            "ck_mailbox_authorization_sessions_purpose_account",
            type_="check",
        )
        batch_op.drop_constraint(
            "ck_mailbox_authorization_sessions_purpose",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_mailbox_authorization_sessions_purpose",
            "purpose IN ('connect', 'reauthorize')",
        )
        batch_op.create_check_constraint(
            "ck_mailbox_authorization_sessions_purpose_account",
            "(purpose = 'connect' AND connector_account_id IS NULL) OR "
            "(purpose = 'reauthorize' AND connector_account_id IS NOT NULL)",
        )

    # SQLite batch recreate of connector_accounts would DROP the old table
    # and cascade-delete reauthorize sessions via connector_account_id FK.
    # Native DROP COLUMN (SQLite 3.35+) and PostgreSQL ALTER keep those rows.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(sa.text("ALTER TABLE connector_accounts DROP COLUMN display_identity"))
    else:
        op.drop_column("connector_accounts", "display_identity")
