"""Phase 21D allow attachment_analyses.kind = xlsx.

Revision ID: 21d0001
Revises: 20c0001
Create Date: 2026-09-19

Extends ck_attachment_analyses_kind to include 'xlsx' so validated XLSX
attachment analyses can persist through the existing attachment_analyses
table, with one nullable structured tabular_result column. No raw workbook storage.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "21d0001"
down_revision: str | None = "20c0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_WITH_XLSX = "kind IN ('pdf', 'docx', 'jpeg', 'png', 'txt', 'xlsx')"
_KIND_WITHOUT_XLSX = "kind IN ('pdf', 'docx', 'jpeg', 'png', 'txt')"


def upgrade() -> None:
    with op.batch_alter_table("attachment_analyses") as batch_op:
        batch_op.add_column(
            sa.Column(
                "tabular_result",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=True,
            )
        )
        batch_op.drop_constraint("ck_attachment_analyses_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_attachment_analyses_kind",
            _KIND_WITH_XLSX,
        )


def downgrade() -> None:
    # Preserve records: operators must retain this revision while XLSX history
    # exists. Refuse before SQLite batch DDL or PostgreSQL constraint changes.
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM attachment_analyses WHERE kind = 'xlsx' LIMIT 1"))
        .first()
        is not None
    ):
        raise RuntimeError("Cannot downgrade 21d0001 while XLSX attachment analyses exist.")
    with op.batch_alter_table("attachment_analyses") as batch_op:
        batch_op.drop_column("tabular_result")
        batch_op.drop_constraint("ck_attachment_analyses_kind", type_="check")
        batch_op.create_check_constraint(
            "ck_attachment_analyses_kind",
            _KIND_WITHOUT_XLSX,
        )
