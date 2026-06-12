"""create crdt tables

Revision ID: b7c4e9d21f08
Revises: df0daad1ac8d
Create Date: 2026-06-09 23:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c4e9d21f08"
down_revision: str | None = "df0daad1ac8d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "crdt_document_state",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("state", sa.LargeBinary(), nullable=False),
        sa.Column("state_vector", sa.LargeBinary(), nullable=False),
        sa.Column("seq", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("text_synced_seq", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.entity_id"],
            name=op.f("fk_crdt_document_state_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_crdt_document_state")),
    )
    op.create_table(
        "crdt_update",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("update", sa.LargeBinary(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.entity_id"],
            name=op.f("fk_crdt_update_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crdt_update")),
    )
    op.create_index(
        "ix_crdt_update_document_id_id", "crdt_update", ["document_id", "id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_crdt_update_document_id_id", table_name="crdt_update")
    op.drop_table("crdt_update")
    op.drop_table("crdt_document_state")
