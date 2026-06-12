"""create agent_audit_log (spec 49)

Revision ID: d1e3f7a69c82
Revises: c9d2e6f58b71
Create Date: 2026-06-10 23:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1e3f7a69c82"
down_revision: str | None = "c9d2e6f58b71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIONS = (
    "'run_start','run_stop','tool_call','tool_result','proposal_created',"
    "'apply_recorded','limit_block','budget_block','injection_flagged','error'"
)


def upgrade() -> None:
    op.create_table(
        "agent_audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("tokens_prompt", sa.Integer(), nullable=True),
        sa.Column("tokens_completion", sa.Integer(), nullable=True),
        sa.Column("cost_estimate_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("outcome", sa.Text(), server_default="ok", nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(f"action IN ({_ACTIONS})", name="agent_audit_action_valid"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_agent_audit_log_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_agent_audit_log_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_audit_log")),
    )
    op.create_index("ix_agent_audit_user_created", "agent_audit_log", ["user_id", "created_at"])
    op.create_index(
        "ix_agent_audit_project_created", "agent_audit_log", ["project_id", "created_at"]
    )
    op.create_index("ix_agent_audit_run", "agent_audit_log", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_audit_run", table_name="agent_audit_log")
    op.drop_index("ix_agent_audit_project_created", table_name="agent_audit_log")
    op.drop_index("ix_agent_audit_user_created", table_name="agent_audit_log")
    op.drop_table("agent_audit_log")
