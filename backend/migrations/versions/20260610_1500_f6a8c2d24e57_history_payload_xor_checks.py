"""history payload/base XOR check constraints (spec 40)

Enforce at the DB level the invariant that exactly one of the inline payload and the
blob key is set, so a future capture/compaction bug cannot silently corrupt a version.

Attribution note (issue 144): these CheckConstraints fulfil spec 36 §5.1.3's
storage-location XOR invariant. They were intentionally added here (under the
spec-40 refactor pass) rather than in the initial spec-36 migration
(``c3d5f7a91b24``); the spec-40 attribution in this title is deliberate. The two
revisions together implement one spec-36 invariant. No DDL is changed by this note.

Revision ID: f6a8c2d24e57
Revises: e5f7b9c13d46
Create Date: 2026-06-10 15:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "f6a8c2d24e57"
down_revision: str | None = "e5f7b9c13d46"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_history_chunks_base_xor",
        "history_chunks",
        "(base_snapshot IS NULL) <> (base_snapshot_blob_key IS NULL)",
    )
    op.create_check_constraint(
        "ck_history_updates_payload_xor",
        "history_updates",
        "(payload IS NULL) <> (payload_blob_key IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_history_updates_payload_xor", "history_updates", type_="check")
    op.drop_constraint("ck_history_chunks_base_xor", "history_chunks", type_="check")
