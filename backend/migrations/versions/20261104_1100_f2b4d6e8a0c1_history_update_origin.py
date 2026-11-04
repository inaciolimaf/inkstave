"""add origin to history_updates (spec 121: git-push)

Revision ID: f2b4d6e8a0c1
Revises: e7a1c3d5b9f2
Create Date: 2026-11-04 11:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b4d6e8a0c1"
down_revision: str | None = "e7a1c3d5b9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable and without a default: every existing row is an editor's own change, so NULL is correct.
    op.add_column("history_updates", sa.Column("origin", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("history_updates", "origin")
