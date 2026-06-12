"""create history_labels table

Revision ID: d4e6a8b02c35
Revises: c3d5f7a91b24
Create Date: 2026-06-10 11:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e6a8b02c35"
down_revision: str | None = "c3d5f7a91b24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("doc_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_history_labels_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.entity_id"],
            name=op.f("fk_history_labels_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_history_labels_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_history_labels")),
    )
    op.create_index("ix_history_labels_doc", "history_labels", ["doc_id", "version"], unique=False)
    op.create_index(
        "ix_history_labels_project", "history_labels", ["project_id", "created_at"], unique=False
    )
    op.create_index(
        "uq_history_labels_doc_name",
        "history_labels",
        ["doc_id", "name"],
        unique=True,
        postgresql_where=sa.text("doc_id IS NOT NULL"),
    )
    op.create_index(
        "uq_history_labels_project_name",
        "history_labels",
        ["project_id", "name"],
        unique=True,
        postgresql_where=sa.text("doc_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_history_labels_project_name", table_name="history_labels")
    op.drop_index("uq_history_labels_doc_name", table_name="history_labels")
    op.drop_index("ix_history_labels_project", table_name="history_labels")
    op.drop_index("ix_history_labels_doc", table_name="history_labels")
    op.drop_table("history_labels")
