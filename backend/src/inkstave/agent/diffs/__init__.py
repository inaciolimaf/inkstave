"""Agent diff generation (spec 43): staged edits → reviewable per-file unified diffs."""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
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
    from inkstave.db.models.document import Document

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


def _note_ignored_ranges(rationale: str | None, edits: list[StagedEdit]) -> str | None:
    """Append the note that a full replacement overrode the range edits, if it did."""
    has_full = any(e.mode == EditMode.full for e in edits)
    has_range = any(e.mode == EditMode.range for e in edits)
    if not (has_full and has_range):
        return rationale
    note = "A full replacement was proposed; range edits were ignored."
    return f"{rationale}\n{note}" if rationale else note


@dataclass(slots=True)
class _Materializer:
    """Turns one document's staged edits into a persisted proposal row."""

    db: AsyncSession
    session: AgentSession
    settings: AgentSettings
    message_id: UUID | None

    async def for_doc(self, doc_id_str: str, edits: list[StagedEdit]) -> ProposedDiff | None:
        """The proposal for one document, or ``None`` when there is nothing to record."""
        document = await self._document(doc_id_str)
        if document is None:
            return None
        current = document.content
        if is_oversized(current, self.settings.agent_diff_max_doc_chars):
            logger.info("materialize_diffs: doc %s too large to diff; skipped", doc_id_str)
            return None

        spec = self._spec(UUID(doc_id_str), document, edits)
        try:
            proposed = apply_staged_edits(current, edits)
        except DiffConflictError as exc:
            # Overlapping ranges: record a rejected proposal; never mis-apply.
            spec.status = ProposedDiffStatus.rejected.value
            spec.rationale = f"Conflicting edits could not be combined: {exc}"
            return await self._persist(spec)

        spec.diff_text, spec.hunks, spec.stats = compute_diff(
            current, proposed, path=spec.path, context=self.settings.agent_diff_context_lines
        )
        if not spec.hunks:
            logger.info("materialize_diffs: doc %s diff is a no-op; skipped", doc_id_str)
            return None
        spec.rationale = _note_ignored_ranges(spec.rationale, edits)
        return await self._persist(spec)

    def _spec(self, doc_id: UUID, document: Document, edits: list[StagedEdit]) -> repo.NewDiff:
        """A row payload pre-filled with everything that does not depend on the diff."""
        return repo.NewDiff(
            session_id=self.session.id,
            message_id=self.message_id,
            project_id=self.session.project_id,
            doc_id=doc_id,
            path=edits[0].path,
            base_version=str(document.version),
            base_hash=content_hash(document.content),
            rationale=_combined_rationale(edits),
        )

    async def _document(self, doc_id_str: str) -> Document | None:
        try:
            return await get_document(self.db, self.session.project_id, UUID(doc_id_str))
        except (ValueError, EntityNotFoundError, NotADocumentError):
            logger.warning("materialize_diffs: doc %s not resolvable; skipped", doc_id_str)
            return None

    async def _persist(self, spec: repo.NewDiff) -> ProposedDiff:
        """Supersede prior open proposals for this doc, then insert the new row."""
        await repo.mark_superseded(self.db, session_id=self.session.id, doc_id=spec.doc_id)
        return await repo.create(self.db, spec)


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
    grouped: OrderedDict[str, list[StagedEdit]] = OrderedDict()
    for edit in state.get("staged_edits", []):
        grouped.setdefault(edit.doc_id, []).append(edit)

    materializer = _Materializer(db, session, settings, message_id)
    rows = [await materializer.for_doc(doc_id, edits) for doc_id, edits in grouped.items()]
    return [row for row in rows if row is not None]


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
