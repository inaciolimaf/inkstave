"""The values the history capture service passes between buffering and writing (spec 36)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from inkstave.modules.collab import YDocument
from inkstave.modules.history.versions.reconstruct import text_from_state

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from inkstave.modules.history.models import HistoryChunk


@dataclass(slots=True)
class Pending:
    """A doc's buffered updates, merged and detached from the buffer."""

    merged: bytes
    op_count: int
    author_id: UUID | None
    at: datetime
    project_id: UUID
    origin: str | None = None


@dataclass(slots=True)
class UpdateEntry:
    """One history row's worth of data, before it is written."""

    chunk: HistoryChunk
    project_id: UUID
    doc_id: UUID
    version: int
    payload: bytes
    op_count: int
    author_id: UUID | None
    at: datetime
    origin: str | None = None

    @classmethod
    def of(cls, chunk: HistoryChunk, doc_id: UUID, version: int, pending: Pending) -> UpdateEntry:
        return cls(
            chunk=chunk,
            project_id=pending.project_id,
            doc_id=doc_id,
            version=version,
            payload=pending.merged,
            op_count=pending.op_count,
            author_id=pending.author_id,
            at=pending.at,
            origin=pending.origin,
        )


@dataclass(slots=True)
class Replica:
    """A doc's history replica and, when it was just rebuilt, the live state it came with."""

    doc: YDocument
    live: bytes | None = None
    from_live: bool = False  # the replica *is* the live state: the doc's first history chunk

    def drifted_from_live(self) -> bool:
        """Whether a replica rebuilt from history disagrees with the live document."""
        if self.live is None or self.from_live:
            return False
        return self.doc.text != text_from_state(self.live)


def doc_from(state: bytes | None) -> YDocument:
    doc = YDocument()
    if state is not None:
        doc.apply_update(state)
    return doc
