"""create proposed_file_ops

Revision ID: c5e9a1b37d42
Revises: b4d8f1a2c6e3
Create Date: 2026-11-02 20:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c5e9a1b37d42"
down_revision: str | None = "b4d8f1a2c6e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposed_file_ops",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("new_path", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("affected_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="proposed", nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('create','delete','move')", name="proposed_file_op_kind_valid"),
        sa.CheckConstraint(
            "status IN ('proposed','applied','rejected','superseded')", name="proposed_file_op_status_valid"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name=op.f("fk_proposed_file_ops_session_id_agent_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["agent_messages.id"],
            name=op.f("fk_proposed_file_ops_message_id_agent_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_proposed_file_ops_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["tree_entities.id"],
            name=op.f("fk_proposed_file_ops_entity_id_tree_entities"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposed_file_ops")),
    )
    op.create_index("ix_proposed_file_ops_session_created", "proposed_file_ops", ["session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_proposed_file_ops_session_created", table_name="proposed_file_ops")
    op.drop_table("proposed_file_ops")
