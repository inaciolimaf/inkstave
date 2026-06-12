"""create history tables (chunks + updates)

Attribution note (issue 144): spec 36 §5.1.3's storage-location XOR invariant
(exactly one of the inline payload and the blob key is set) is *not* enforced in
this migration. Those CheckConstraints were deferred to a later migration,
``f6a8c2d24e57`` ("history payload/base XOR check constraints"), added under the
spec-40 refactor pass. The constraints exist at head; this is the same spec-36
invariant, just split across two revisions. No schema change here.

Revision ID: c3d5f7a91b24
Revises: a1c2e3f40915
Create Date: 2026-06-10 09:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d5f7a91b24"
down_revision: str | None = "a1c2e3f40915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("doc_id", sa.UUID(), nullable=False),
        sa.Column("start_version", sa.BigInteger(), nullable=False),
        sa.Column("end_version", sa.BigInteger(), nullable=False),
        sa.Column("base_version", sa.BigInteger(), nullable=False),
        sa.Column("base_snapshot", sa.LargeBinary(), nullable=True),
        sa.Column("base_snapshot_blob_key", sa.Text(), nullable=True),
        sa.Column("base_snapshot_size", sa.Integer(), nullable=False),
        sa.Column("sealed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_history_chunks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.entity_id"],
            name=op.f("fk_history_chunks_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_history_chunks")),
    )
    op.create_index(
        "ix_history_chunks_doc_version", "history_chunks", ["doc_id", "start_version"], unique=False
    )
    op.create_index(
        "ix_history_chunks_project", "history_chunks", ["project_id", "created_at"], unique=False
    )
    op.create_index(
        "uq_history_chunks_open",
        "history_chunks",
        ["doc_id"],
        unique=True,
        postgresql_where=sa.text("sealed = false"),
    )

    op.create_table(
        "history_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("doc_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("payload", sa.LargeBinary(), nullable=True),
        sa.Column("payload_blob_key", sa.Text(), nullable=True),
        sa.Column("payload_size", sa.Integer(), nullable=False),
        sa.Column("op_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["history_chunks.id"],
            name=op.f("fk_history_updates_chunk_id_history_chunks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_history_updates_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.entity_id"],
            name=op.f("fk_history_updates_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_history_updates_author_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_history_updates")),
    )
    op.create_index(
        "uq_history_updates_doc_version", "history_updates", ["doc_id", "version"], unique=True
    )
    op.create_index(
        "ix_history_updates_chunk", "history_updates", ["chunk_id", "version"], unique=False
    )
    op.create_index(
        "ix_history_updates_project_ts", "history_updates", ["project_id", "timestamp"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_history_updates_project_ts", table_name="history_updates")
    op.drop_index("ix_history_updates_chunk", table_name="history_updates")
    op.drop_index("uq_history_updates_doc_version", table_name="history_updates")
    op.drop_table("history_updates")
    op.drop_index("uq_history_chunks_open", table_name="history_chunks")
    op.drop_index("ix_history_chunks_project", table_name="history_chunks")
    op.drop_index("ix_history_chunks_doc_version", table_name="history_chunks")
    op.drop_table("history_chunks")
