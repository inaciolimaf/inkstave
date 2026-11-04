"""spell-check language per project and the personal dictionary (spec 113)

Revision ID: 4dd4cd5a3e49
Revises: c5e9a1b37d42
Create Date: 2026-11-04 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4dd4cd5a3e49"
down_revision: str | None = "c5e9a1b37d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("spellcheck_language", sa.Text(), server_default=sa.text("'en-US'"), nullable=False),
    )
    op.create_check_constraint(
        "ck_projects_spellcheck_language_valid",
        "projects",
        "spellcheck_language IN ('off', 'en-US', 'pt-BR')",
    )
    op.create_table(
        "user_dictionary_words",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("word", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_dictionary_words_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_user_dictionary_words_user_lower_word",
        "user_dictionary_words",
        ["user_id", sa.text("lower(word)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_user_dictionary_words_user_lower_word", table_name="user_dictionary_words")
    op.drop_table("user_dictionary_words")
    op.drop_constraint("ck_projects_spellcheck_language_valid", "projects", type_="check")
    op.drop_column("projects", "spellcheck_language")
