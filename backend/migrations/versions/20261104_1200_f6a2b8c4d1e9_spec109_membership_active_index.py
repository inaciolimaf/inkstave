"""index active memberships by user for the shared projects listing (spec 109)

Revision ID: f6a2b8c4d1e9
Revises: c5e9a1b37d42
Create Date: 2026-11-04 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a2b8c4d1e9"
down_revision: str | None = "c5e9a1b37d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_project_memberships_user_active",
        "project_memberships",
        ["user_id", "project_id"],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ix_project_memberships_user_active", table_name="project_memberships")
