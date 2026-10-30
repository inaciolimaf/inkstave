"""add session revocation

Revision ID: b4d8f1a2c6e3
Revises: a3c7e9d21f44
Create Date: 2026-10-30 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4d8f1a2c6e3"
down_revision: str | None = "a3c7e9d21f44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Constant defaults: Postgres records them in the catalog without rewriting `users`.
    op.add_column(
        "users", sa.Column("session_version", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False)
    )
    op.create_table(
        "revoked_sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_revoked_sessions")),
    )
    op.create_index("ix_revoked_sessions_expires_at", "revoked_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_revoked_sessions_expires_at", table_name="revoked_sessions")
    op.drop_table("revoked_sessions")
    op.drop_column("users", "is_active")
    op.drop_column("users", "session_version")
