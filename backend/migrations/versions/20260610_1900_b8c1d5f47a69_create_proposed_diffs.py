"""create proposed_diffs (spec 43)

Revision ID: b8c1d5f47a69
Revises: a7b9d3e35f68
Create Date: 2026-06-10 19:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c1d5f47a69"
down_revision: str | None = "a7b9d3e35f68"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = "'proposed','applied','partially_applied','rejected','stale','superseded'"


def upgrade() -> None:
    op.create_table(
        "proposed_diffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("doc_id", sa.UUID(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("base_version", sa.Text(), nullable=False),
        sa.Column("base_hash", sa.Text(), nullable=False),
        sa.Column("diff_text", sa.Text(), nullable=False),
        sa.Column("hunks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="proposed", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(f"status IN ({_STATUS})", name="proposed_diff_status_valid"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name=op.f("fk_proposed_diffs_session_id_agent_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["agent_messages.id"],
            name=op.f("fk_proposed_diffs_message_id_agent_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_proposed_diffs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["doc_id"],
            ["documents.entity_id"],
            name=op.f("fk_proposed_diffs_doc_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposed_diffs")),
    )
    op.create_index(
        "ix_proposed_diffs_session_created", "proposed_diffs", ["session_id", "created_at"]
    )
    op.create_index(
        "ix_proposed_diffs_project_status", "proposed_diffs", ["project_id", "status"]
    )
    op.create_index("ix_proposed_diffs_doc", "proposed_diffs", ["doc_id"])


def downgrade() -> None:
    op.drop_index("ix_proposed_diffs_doc", table_name="proposed_diffs")
    op.drop_index("ix_proposed_diffs_project_status", table_name="proposed_diffs")
    op.drop_index("ix_proposed_diffs_session_created", table_name="proposed_diffs")
    op.drop_table("proposed_diffs")
