"""project_imports: source, compatibility report and its seen marker (spec 120)

Revision ID: d6a0b2c4e8f1
Revises: c5e9a1b37d42
Create Date: 2026-11-04 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d6a0b2c4e8f1"
down_revision: str | None = "c5e9a1b37d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_imports",
        sa.Column("source", sa.String(length=32), server_default="zip", nullable=False),
    )
    op.add_column(
        "project_imports",
        sa.Column("compat_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "project_imports",
        sa.Column("report_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_project_imports_project_import_source_valid"),
        "project_imports",
        "source IN ('zip','overleaf_template')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_project_imports_project_import_source_valid"), "project_imports", type_="check"
    )
    op.drop_column("project_imports", "report_seen_at")
    op.drop_column("project_imports", "compat_report")
    op.drop_column("project_imports", "source")
