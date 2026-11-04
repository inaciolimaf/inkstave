"""suggest mode on project memberships (spec 119)

Revision ID: c3d5f7a9b1e2
Revises: b7e1c4d9a2f6
Create Date: 2026-11-04 19:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d5f7a9b1e2"
down_revision: str | None = "b7e1c4d9a2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_memberships",
        sa.Column("suggest_mode", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("project_memberships", "suggest_mode")
