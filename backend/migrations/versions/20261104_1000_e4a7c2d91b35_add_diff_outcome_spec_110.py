"""record the outcome of a proposed diff (spec 110)

Revision ID: e4a7c2d91b35
Revises: a8d3c5e1f7b2
Create Date: 2026-11-04 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4a7c2d91b35"
down_revision: str | None = "a8d3c5e1f7b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIONS_BEFORE = (
    "'run_start','run_stop','tool_call','tool_result','proposal_created',"
    "'apply_recorded','limit_block','budget_block','injection_flagged','error'"
)
_ACTIONS_AFTER = _ACTIONS_BEFORE + ",'proposal_decided'"


def upgrade() -> None:
    op.add_column(
        "proposed_diffs",
        sa.Column("decided_hunks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("proposed_diffs", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("proposed_diffs", sa.Column("decided_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_proposed_diffs_decided_by_users"),
        "proposed_diffs",
        "users",
        ["decided_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("agent_audit_action_valid", "agent_audit_log", type_="check")
    op.create_check_constraint("agent_audit_action_valid", "agent_audit_log", f"action IN ({_ACTIONS_AFTER})")


def downgrade() -> None:
    op.execute("DELETE FROM agent_audit_log WHERE action = 'proposal_decided'")
    op.drop_constraint("agent_audit_action_valid", "agent_audit_log", type_="check")
    op.create_check_constraint(
        "agent_audit_action_valid", "agent_audit_log", f"action IN ({_ACTIONS_BEFORE})"
    )
    op.drop_constraint(op.f("fk_proposed_diffs_decided_by_users"), "proposed_diffs", type_="foreignkey")
    op.drop_column("proposed_diffs", "decided_by")
    op.drop_column("proposed_diffs", "decided_at")
    op.drop_column("proposed_diffs", "decided_hunks")
