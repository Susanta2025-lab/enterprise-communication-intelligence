"""Phase 12A execution-target provenance.

Revision ID: 12a0001
Revises: 11b0001
Create Date: 2026-08-22

Adds nullable mailbox-routing provenance. There is no foreign key from
analyses.connector_account_id or workflow_actions.connector_account_id to
connector_accounts. Existing rows remain valid with NULL values.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "12a0001"
down_revision: str | None = "11b0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("connector_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "workflow_actions",
        sa.Column("connector_account_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "workflow_actions",
        sa.Column("provider_message_id", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_workflow_actions_execution_target",
        "workflow_actions",
        "(connector_account_id IS NULL) = (provider_message_id IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_workflow_actions_execution_target",
        "workflow_actions",
        type_="check",
    )
    op.drop_column("workflow_actions", "provider_message_id")
    op.drop_column("workflow_actions", "connector_account_id")
    op.drop_column("analyses", "connector_account_id")
