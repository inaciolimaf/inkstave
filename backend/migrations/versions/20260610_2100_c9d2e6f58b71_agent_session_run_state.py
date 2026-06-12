"""agent_sessions run-state columns (spec 44)

Revision ID: c9d2e6f58b71
Revises: b8c1d5f47a69
Create Date: 2026-06-10 21:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d2e6f58b71"
down_revision: str | None = "b8c1d5f47a69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_sessions", sa.Column("active_run_id", sa.UUID(), nullable=True))
    op.add_column(
        "agent_sessions",
        sa.Column(
            "run_state", sa.String(length=16), server_default="idle", nullable=False
        ),
    )
    op.create_check_constraint(
        "agent_session_run_state_valid",
        "agent_sessions",
        "run_state IN ('idle','queued','running','cancelling','done','error')",
    )


def downgrade() -> None:
    op.drop_constraint("agent_session_run_state_valid", "agent_sessions", type_="check")
    op.drop_column("agent_sessions", "run_state")
    op.drop_column("agent_sessions", "active_run_id")
