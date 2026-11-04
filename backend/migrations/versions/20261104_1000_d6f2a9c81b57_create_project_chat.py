"""create project chat tables

Revision ID: d6f2a9c81b57
Revises: f6a2b8c4d1e9
Create Date: 2026-11-04 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6f2a9c81b57"
down_revision: str | None = "f6a2b8c4d1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_chat_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name=op.f("ck_project_chat_messages_body_length")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_chat_messages_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_project_chat_messages_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_chat_messages")),
    )
    op.create_index(
        "ix_project_chat_messages_project_created",
        "project_chat_messages",
        ["project_id", sa.text("created_at DESC"), "id"],
        unique=False,
    )
    op.create_table(
        "project_chat_reads",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_chat_reads_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_chat_reads_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "user_id", name=op.f("pk_project_chat_reads")),
    )


def downgrade() -> None:
    op.drop_table("project_chat_reads")
    op.drop_index("ix_project_chat_messages_project_created", table_name="project_chat_messages")
    op.drop_table("project_chat_messages")
