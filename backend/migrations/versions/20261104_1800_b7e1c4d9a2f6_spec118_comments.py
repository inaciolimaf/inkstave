"""comment threads and messages (spec 118)

Revision ID: b7e1c4d9a2f6
Revises: f2b4d6e8a0c1
Create Date: 2026-11-04 18:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e1c4d9a2f6"
down_revision: str | None = "f2b4d6e8a0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("anchor_start", sa.LargeBinary(), nullable=False),
        sa.Column("anchor_end", sa.LargeBinary(), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "octet_length(anchor_start) BETWEEN 1 AND 256",
            name=op.f("ck_comment_threads_anchor_start_size"),
        ),
        sa.CheckConstraint(
            "octet_length(anchor_end) BETWEEN 1 AND 256",
            name=op.f("ck_comment_threads_anchor_end_size"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_comment_threads_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["tree_entities.id"],
            name=op.f("fk_comment_threads_document_id_tree_entities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_comment_threads_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_comment_threads_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment_threads")),
    )
    op.create_index(
        "ix_comment_threads_project_document",
        "comment_threads",
        ["project_id", "document_id"],
        unique=False,
    )
    op.create_index(
        "ix_comment_threads_open",
        "comment_threads",
        ["project_id", "document_id"],
        unique=False,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_table(
        "comment_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "mentions",
            postgresql.ARRAY(sa.UUID()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(body) BETWEEN 1 AND 4000",
            name=op.f("ck_comment_messages_body_length"),
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["comment_threads.id"],
            name=op.f("fk_comment_messages_thread_id_comment_threads"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_comment_messages_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comment_messages")),
    )
    op.create_index(
        "ix_comment_messages_thread_created",
        "comment_messages",
        ["thread_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_comment_messages_thread_created", table_name="comment_messages")
    op.drop_table("comment_messages")
    op.drop_index("ix_comment_threads_open", table_name="comment_threads")
    op.drop_index("ix_comment_threads_project_document", table_name="comment_threads")
    op.drop_table("comment_threads")
