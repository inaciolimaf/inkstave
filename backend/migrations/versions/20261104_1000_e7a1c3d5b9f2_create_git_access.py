"""create git access tokens and repo state (spec 121)

Revision ID: e7a1c3d5b9f2
Revises: 4dd4cd5a3e49
Create Date: 2026-11-04 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1c3d5b9f2"
down_revision: str | None = "4dd4cd5a3e49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "git_access_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 100", name=op.f("ck_git_access_tokens_name_length")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_git_access_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_git_access_tokens")),
    )
    op.create_index("uq_git_access_tokens_token_hash", "git_access_tokens", ["token_hash"], unique=True)
    op.create_index("ix_git_access_tokens_user_id", "git_access_tokens", ["user_id"], unique=False)

    op.create_table(
        "git_repo_state",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("head", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_git_repo_state_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f("pk_git_repo_state")),
    )


def downgrade() -> None:
    op.drop_table("git_repo_state")
    op.drop_index("ix_git_access_tokens_user_id", table_name="git_access_tokens")
    op.drop_index("uq_git_access_tokens_token_hash", table_name="git_access_tokens")
    op.drop_table("git_access_tokens")
