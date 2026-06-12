"""CRDT persistence: snapshot + append-only update log in Postgres (spec 28)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pycrdt import merge_updates
from sqlalchemy import delete, func, select

from inkstave.db.models.crdt import CrdtDocumentState, CrdtUpdate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

SessionFactory = Callable[[], AbstractAsyncContextManager["AsyncSession"]]


class CrdtStore:
    """Durable CRDT state. Loading is **snapshot first, then ordered log**; the
    append path is a single INSERT (no read of the existing log)."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    async def load(self, document_id: UUID) -> tuple[bytes | None, int]:
        """Return ``(full_state_or_None, seq)`` by merging the snapshot with every
        ``crdt_update`` row in id order."""
        async with self._session_factory() as session:
            state_row = await session.get(CrdtDocumentState, document_id)
            updates = (
                await session.execute(
                    select(CrdtUpdate.update)
                    .where(CrdtUpdate.document_id == document_id)
                    .order_by(CrdtUpdate.id)
                )
            ).scalars()
            update_list = list(updates)

        parts: list[bytes] = []
        if state_row is not None:
            parts.append(state_row.state)
        parts.extend(update_list)
        seq = state_row.seq if state_row is not None else 0
        if not parts:
            return None, seq
        merged = parts[0] if len(parts) == 1 else merge_updates(*parts)
        return merged, seq

    async def append_update(self, document_id: UUID, update: bytes, origin: str | None) -> int:
        """Append one update row (O(1) INSERT) and return its id."""
        async with self._session_factory() as session:
            row = CrdtUpdate(document_id=document_id, update=update, origin=origin)
            session.add(row)
            await session.flush()
            new_id = row.id
            await session.commit()
            return new_id

    async def snapshot(
        self,
        *,
        document_id: UUID,
        state: bytes,
        state_vector: bytes,
        upto_update_id: int | None,
    ) -> int:
        """Compaction: write ``state``/``state_vector``, bump ``seq``, and delete
        ``crdt_update`` rows with ``id <= upto_update_id`` — all in one
        transaction. Returns the new ``seq``."""
        async with self._session_factory() as session:
            row = await session.get(CrdtDocumentState, document_id)
            now = datetime.now(UTC)
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
                new_seq = 1
            else:
                row.state = state
                row.state_vector = state_vector
                row.seq += 1
                row.updated_at = now
                new_seq = row.seq
            if upto_update_id is not None:
                await session.execute(
                    delete(CrdtUpdate).where(
                        CrdtUpdate.document_id == document_id, CrdtUpdate.id <= upto_update_id
                    )
                )
            await session.commit()
            return new_seq

    async def max_update_id(self, document_id: UUID) -> int:
        """The current high-water-mark update id (0 if the log is empty)."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.max(CrdtUpdate.id)).where(CrdtUpdate.document_id == document_id)
            )
            return result.scalar() or 0

    async def mark_text_synced(self, document_id: UUID, seq: int) -> None:
        async with self._session_factory() as session:
            row = await session.get(CrdtDocumentState, document_id)
            if row is not None:
                row.text_synced_seq = seq
                await session.commit()
