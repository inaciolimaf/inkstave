"""CRDT persistence: snapshot + append-only update log in Postgres (spec 28).

Every operation that reads the stored state runs in one transaction under a per-document
Postgres advisory lock, so replicas that share the database serialise on it. A write
always carries the merge of the stored state, never one replica's partial view, and a
compaction deletes only the log rows it has merged into the snapshot (ADR 0123).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pycrdt import merge_updates
from sqlalchemy import delete, func, select

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.collab.models import CrdtDocumentState, CrdtUpdate
from inkstave.modules.projects import read_content_for_collab

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

SessionFactory = Callable[[], AbstractAsyncContextManager["AsyncSession"]]
# Writes flushed text into documents.content inside the caller's transaction.
TextWriter = Callable[["AsyncSession", UUID, str], Awaitable[object]]


def _merge(parts: Sequence[bytes]) -> bytes:
    return parts[0] if len(parts) == 1 else merge_updates(*parts)


def _text_of(state: bytes | None) -> str:
    if state is None:
        return ""
    doc = YDocument()
    doc.apply_update(state)
    return doc.text


def _state_vector_of(state: bytes) -> bytes:
    doc = YDocument()
    doc.apply_update(state)
    return doc.get_state_vector()


async def _lock_document(session: AsyncSession, document_id: UUID) -> None:
    """Serialise this transaction with every other writer or reader of the document."""
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"crdt:{document_id}", 0))))


async def _read_stored(
    session: AsyncSession, document_id: UUID
) -> tuple[CrdtDocumentState | None, list[tuple[int, bytes]]]:
    """The snapshot row and the log rows (id, update) in id order, read under the lock."""
    row = await session.get(CrdtDocumentState, document_id, populate_existing=True)
    result = await session.execute(
        select(CrdtUpdate.id, CrdtUpdate.update)
        .where(CrdtUpdate.document_id == document_id)
        .order_by(CrdtUpdate.id)
    )
    return row, [(int(log_id), update) for log_id, update in result.all()]


def _stored_parts(row: CrdtDocumentState | None, rows: list[tuple[int, bytes]]) -> list[bytes]:
    parts = [row.state] if row is not None else []
    return parts + [update for _, update in rows]


async def _write_snapshot(
    session: AsyncSession,
    document_id: UUID,
    row: CrdtDocumentState | None,
    state: bytes,
    delete_ids: list[int],
) -> int:
    """Store ``state`` as the snapshot and drop the log rows ``delete_ids``. Returns the new seq."""
    now = datetime.now(UTC)
    state_vector = _state_vector_of(state)
    if row is None:
        row = CrdtDocumentState(
            document_id=document_id,
            state=state,
            state_vector=state_vector,
            seq=1,
            text_synced_seq=0,
            updated_at=now,
        )
        session.add(row)
    else:
        row.state = state
        row.state_vector = state_vector
        row.seq += 1
        row.updated_at = now
    if delete_ids:
        await session.execute(delete(CrdtUpdate).where(CrdtUpdate.id.in_(delete_ids)))
    return row.seq


class CrdtStore:
    """Durable CRDT state. Loading is **snapshot first, then ordered log**; the
    append path is a single INSERT (no read of the existing log)."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def load(self, document_id: UUID, *, seed: bool = False) -> tuple[bytes | None, int]:
        """Return ``(full_state_or_None, seq)`` by merging the snapshot with every log row.

        With ``seed``, an empty text is first seeded from ``documents.content`` under the lock,
        so two replicas opening a never-edited document cannot both seed it.
        """
        async with self._session_factory() as session:
            await _lock_document(session, document_id)
            row, rows = await _read_stored(session, document_id)
            parts = _stored_parts(row, rows)
            state = _merge(parts) if parts else None
            seq = row.seq if row is not None else 0
            if seed and not _text_of(state):
                seeded = await read_content_for_collab(session, document_id)
                if seeded:
                    doc = YDocument()
                    if state is not None:
                        doc.apply_update(state)
                    doc.replace_text(seeded)
                    state = doc.get_state()
                    seq = await _write_snapshot(session, document_id, row, state, [i for i, _ in rows])
            await session.commit()
            return state, seq

    async def append_update(self, document_id: UUID, update: bytes, origin: str | None) -> int:
        """Append one update row (O(1) INSERT) and return its id."""
        async with self._session_factory() as session:
            row = CrdtUpdate(document_id=document_id, update=update, origin=origin)
            session.add(row)
            await session.flush()
            new_id = row.id
            await session.commit()
            return new_id

    async def snapshot(self, *, document_id: UUID, state: bytes, upto_update_id: int | None) -> int:
        """Compaction: merge ``state`` with the stored snapshot and the log, store the result,
        and delete the log rows it covers with ``id <= upto_update_id`` (all rows when None).

        The stored snapshot only ever grows, so a stale ``state`` cannot drop text another replica
        already compacted. Returns the new ``seq``.
        """
        async with self._session_factory() as session:
            await _lock_document(session, document_id)
            row, rows = await _read_stored(session, document_id)
            merged = _merge([*_stored_parts(row, rows), state])
            covered = [log_id for log_id, _ in rows if upto_update_id is None or log_id <= upto_update_id]
            seq = await _write_snapshot(session, document_id, row, merged, covered)
            await session.commit()
            return seq

    async def flush_text(
        self, document_id: UUID, memory_state: bytes | None, write_text: TextWriter
    ) -> tuple[bytes | None, int]:
        """Write the text of the merged state into ``documents.content``, in one transaction under
        the lock. The merge covers the stored state, every log row and ``memory_state``, so the text
        written is never older than what any replica has acknowledged. Returns ``(merged, seq)``.
        """
        async with self._session_factory() as session:
            await _lock_document(session, document_id)
            row, rows = await _read_stored(session, document_id)
            parts = _stored_parts(row, rows)
            if memory_state is not None:
                parts.append(memory_state)
            if not parts:
                await session.commit()
                return None, 0
            merged = _merge(parts)
            seq = row.seq if row is not None else 0
            await write_text(session, document_id, _text_of(merged))
            if row is not None:
                row.text_synced_seq = seq
            await session.commit()
            return merged, seq
