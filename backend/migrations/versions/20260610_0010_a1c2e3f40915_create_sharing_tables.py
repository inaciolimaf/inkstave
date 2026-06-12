"""create sharing tables (memberships + invites)

Revision ID: a1c2e3f40915
Revises: b7c4e9d21f08
Create Date: 2026-06-10 00:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1c2e3f40915"
down_revision: str | None = "b7c4e9d21f08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
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
            "role IN ('owner','editor','viewer')",
            name=op.f("ck_project_memberships_membership_role_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('active','pending','left')",
            name=op.f("ck_project_memberships_membership_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_memberships_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_project_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_memberships")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_membership_project_user"),
    )
    op.create_index(
        "ix_project_memberships_project_id", "project_memberships", ["project_id"], unique=False
    )
    op.create_index(
        "ix_project_memberships_user_id", "project_memberships", ["user_id"], unique=False
    )
    op.create_index(
        "uq_membership_one_owner",
        "project_memberships",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )

    op.create_table(
        "project_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("invited_by", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
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
            "role IN ('editor','viewer')", name=op.f("ck_project_invites_invite_role_valid")
        ),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','expired')",
            name=op.f("ck_project_invites_invite_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_invites_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_project_invites_invited_by_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_invites")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_project_invites_token_hash")),
    )
    op.create_index(
        "ix_project_invites_project_id_email",
        "project_invites",
        ["project_id", "email"],
        unique=False,
    )
    op.create_index(
        "uq_invite_one_pending",
        "project_invites",
        ["project_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Backfill: every existing live project's owner becomes an active owner member.
    op.execute(
        """
        INSERT INTO project_memberships (id, project_id, user_id, role, status, created_at, updated_at)
        SELECT gen_random_uuid(), p.id, p.owner_id, 'owner', 'active', now(), now()
        FROM projects p
        WHERE p.deleted_at IS NULL
        ON CONFLICT (project_id, user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("uq_invite_one_pending", table_name="project_invites")
    op.drop_index("ix_project_invites_project_id_email", table_name="project_invites")
    op.drop_table("project_invites")
    op.drop_index("uq_membership_one_owner", table_name="project_memberships")
    op.drop_index("ix_project_memberships_user_id", table_name="project_memberships")
    op.drop_index("ix_project_memberships_project_id", table_name="project_memberships")
    op.drop_table("project_memberships")
