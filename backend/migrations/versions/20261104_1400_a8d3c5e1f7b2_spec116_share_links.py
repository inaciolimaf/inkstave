"""share links: project_share_links table and membership link columns (spec 116)

Revision ID: a8d3c5e1f7b2
Revises: f6a2b8c4d1e9
Create Date: 2026-11-04 14:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d3c5e1f7b2"
down_revision: str | None = "f6a2b8c4d1e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_share_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('viewer','editor')", name=op.f("ck_project_share_links_share_link_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_share_links_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_project_share_links_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_share_links")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_project_share_links_token_hash")),
    )
    op.create_index(
        "uq_share_link_one_active",
        "project_share_links",
        ["project_id", "role"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.add_column("project_memberships", sa.Column("via_link_id", sa.Uuid(), nullable=True))
    op.add_column("project_memberships", sa.Column("role_before_link", sa.String(length=16), nullable=True))
    op.create_foreign_key(
        op.f("fk_project_memberships_via_link_id_project_share_links"),
        "project_memberships",
        "project_share_links",
        ["via_link_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        op.f("ck_project_memberships_membership_role_before_link_valid"),
        "project_memberships",
        "role_before_link IS NULL OR role_before_link IN ('viewer','editor')",
    )
    op.create_index(
        "ix_project_memberships_via_link_id",
        "project_memberships",
        ["via_link_id"],
        unique=False,
        postgresql_where=sa.text("via_link_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_project_memberships_via_link_id", table_name="project_memberships")
    op.drop_constraint(
        op.f("ck_project_memberships_membership_role_before_link_valid"),
        "project_memberships",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_project_memberships_via_link_id_project_share_links"),
        "project_memberships",
        type_="foreignkey",
    )
    op.drop_column("project_memberships", "role_before_link")
    op.drop_column("project_memberships", "via_link_id")
    op.drop_index("uq_share_link_one_active", table_name="project_share_links")
    op.drop_table("project_share_links")
