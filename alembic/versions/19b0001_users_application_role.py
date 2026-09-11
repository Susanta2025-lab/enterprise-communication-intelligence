"""Phase 19B application role on users.

Revision ID: 19b0001
Revises: 18d0001
Create Date: 2026-09-11

Adds constrained users.application_role (user | owner), default user.
Existing rows become user. Does not create owners. Does not change
external_identities, mailbox, or communications permission semantics.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "19b0001"
down_revision: str | None = "18d0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "application_role",
                sa.Text(),
                nullable=False,
                server_default="user",
            )
        )
        batch_op.create_check_constraint(
            "ck_users_application_role",
            "application_role IN ('user', 'owner')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_application_role", type_="check")
        batch_op.drop_column("application_role")
