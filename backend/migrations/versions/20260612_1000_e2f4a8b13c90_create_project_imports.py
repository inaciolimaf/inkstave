"""create project_imports

Revision ID: e2f4a8b13c90
Revises: fda790a9deeb
Create Date: 2026-06-12 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f4a8b13c90"
down_revision: str | None = "fda790a9deeb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_imports",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("source_bytes", sa.BigInteger(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("entries_total", sa.Integer(), nullable=True),
        sa.Column("entries_imported", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','success','partial','failure','error')",
            name=op.f("ck_project_imports_project_import_status_valid"),
        ),
        sa.CheckConstraint(
            "source_bytes >= 0", name=op.f("ck_project_imports_project_import_source_bytes_nonneg")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_imports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_project_imports_requested_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_imports")),
    )
    op.create_index(
        "ix_project_imports_project_id", "project_imports", ["project_id"], unique=False
    )
    op.create_index(
        "ix_project_imports_requester",
        "project_imports",
        ["requested_by", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_imports_requester", table_name="project_imports")
    op.drop_index("ix_project_imports_project_id", table_name="project_imports")
    op.drop_table("project_imports")
