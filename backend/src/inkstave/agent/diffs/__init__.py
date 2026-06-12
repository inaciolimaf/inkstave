"""Agent diff generation (spec 43): staged edits → reviewable per-file unified diffs."""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.agent.diffs import repository as repo
from inkstave.agent.diffs.compute import (
    DiffConflictError,
    apply_staged_edits,
    compute_diff,
    content_hash,
)
from inkstave.agent.diffs.models import ProposedDiff, ProposedDiffStatus
from inkstave.agent.edits import EditMode
from inkstave.services.document_service import NotADocumentError, get_document
from inkstave.services.tree_service import EntityNotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.agent.edits import StagedEdit
    from inkstave.agent.models import AgentSession
    from inkstave.agent.settings import AgentSettings
    from inkstave.agent.state import AgentState

logger = logging.getLogger("inkstave.agent.diffs")


def is_stale(diff: ProposedDiff, current_text: str, current_version: object) -> bool:
    """True when the doc no longer matches the diff's recorded base (version or hash)."""
    return str(current_version) != diff.base_version or content_hash(current_text) != diff.base_hash


def _combined_rationale(edits: list[StagedEdit]) -> str | None:
    parts = [e.rationale for e in edits if e.rationale]
    return "\n".join(parts) if parts else None


def is_oversized(content: str, max_doc_chars: int) -> bool:
    """True when ``content`` exceeds the diffable size budget (spec 43, AC 9).

    Pure helper so the oversized-skip branch can be unit-tested without a DB;
    ``materialize_diffs`` uses it to skip diffing very large documents.
    """
    return len(content) > max_doc_chars


async def materialize_diffs(
    *,
    state: AgentState,
    settings: AgentSettings,
    db: AsyncSession,
    session: AgentSession,
    message_id: UUID | None,
) -> list[ProposedDiff]:
    """Turn ``state.staged_edits`` into persisted ``proposed_diffs`` rows.

    Fetches each doc's current content/version freshly, computes the diff, supersedes
    prior open proposals, and inserts one row per changed doc. No document is mutated.
    """
    staged = state.get("staged_edits", [])
    if not staged:
        return []

    grouped: OrderedDict[str, list[StagedEdit]] = OrderedDict()
    for edit in staged:
        grouped.setdefault(edit.doc_id, []).append(edit)

    created: list[ProposedDiff] = []
    for doc_id_str, edits in grouped.items():
        try:
            doc_id = UUID(doc_id_str)
            document = await get_document(db, session.project_id, doc_id)
        except (ValueError, EntityNotFoundError, NotADocumentError):
            logger.warning("materialize_diffs: doc %s not resolvable; skipped", doc_id_str)
            continue

        current = document.content
        path = edits[0].path
        if is_oversized(current, settings.agent_diff_max_doc_chars):
            logger.info("materialize_diffs: doc %s too large to diff; skipped", doc_id_str)
            continue

        base_version = str(document.version)
        base = content_hash(current)
        has_full = any(e.mode == EditMode.full for e in edits)
        has_range = any(e.mode == EditMode.range for e in edits)
        rationale = _combined_rationale(edits)

        try:
            proposed = apply_staged_edits(current, edits)
        except DiffConflictError as exc:
            # Overlapping ranges: record a rejected proposal; never mis-apply.
            await repo.mark_superseded(db, session_id=session.id, doc_id=doc_id)
            created.append(
                await repo.create(
                    db,
                    session_id=session.id,
                    message_id=message_id,
                    project_id=session.project_id,
                    doc_id=doc_id,
                    path=path,
                    base_version=base_version,
                    base_hash=base,
                    diff_text="",
                    hunks=[],
                    stats={"additions": 0, "deletions": 0, "hunk_count": 0},
                    status=ProposedDiffStatus.rejected.value,
                    rationale=f"Conflicting edits could not be combined: {exc}",
                )
            )
            continue

        diff_text, hunks, stats = compute_diff(
            current, proposed, path=path, context=settings.agent_diff_context_lines
        )
        if not hunks:
            logger.info("materialize_diffs: doc %s diff is a no-op; skipped", doc_id_str)
            continue

        if has_full and has_range:
            note = "A full replacement was proposed; range edits were ignored."
            rationale = f"{rationale}\n{note}" if rationale else note

        await repo.mark_superseded(db, session_id=session.id, doc_id=doc_id)
        created.append(
            await repo.create(
                db,
                session_id=session.id,
                message_id=message_id,
                project_id=session.project_id,
                doc_id=doc_id,
                path=path,
                base_version=base_version,
                base_hash=base,
                diff_text=diff_text,
                hunks=hunks,
                stats=stats,
                status=ProposedDiffStatus.proposed.value,
                rationale=rationale,
            )
        )

    return created


__all__ = [
    "DiffConflictError",
    "ProposedDiff",
    "ProposedDiffStatus",
    "apply_staged_edits",
    "compute_diff",
    "content_hash",
    "is_oversized",
    "is_stale",
    "materialize_diffs",
    "repo",
]
