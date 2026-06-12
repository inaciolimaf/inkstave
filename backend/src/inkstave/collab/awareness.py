"""In-memory awareness registry (spec 28). Ephemeral — never persisted."""

from __future__ import annotations

from uuid import UUID

from pycrdt import Awareness, Doc


class AwarenessRegistry:
    """Tracks per-document awareness state in memory so a newly joined client can
    receive a full snapshot and disconnects can be broadcast. Awareness is
    per-connection and cleared on disconnect; nothing is written to the database."""

    def __init__(self) -> None:
        self._by_document: dict[UUID, Awareness] = {}

    def _awareness(self, document_id: UUID) -> Awareness:
        awareness = self._by_document.get(document_id)
        if awareness is None:
            # A throwaway Doc backs the clock; the server sets no local state.
            awareness = Awareness(Doc())
            self._by_document[document_id] = awareness
        return awareness

    def apply(self, document_id: UUID, update: bytes) -> bytes:
        """Merge an awareness update and return the blob to relay to other clients."""
        awareness = self._awareness(document_id)
        awareness.apply_awareness_update(update, origin="remote")
        return update

    def remove_client(self, document_id: UUID, client_id: int) -> bytes | None:
        """Produce an awareness update marking ``client_id`` offline (on disconnect)."""
        awareness = self._by_document.get(document_id)
        if awareness is None or client_id not in awareness.states:
            return None
        awareness.remove_awareness_states([client_id], origin="disconnect")
        return awareness.encode_awareness_update([client_id])

    def snapshot(self, document_id: UUID) -> bytes | None:
        """Full awareness state to send to a newly joined client, or None if empty."""
        awareness = self._by_document.get(document_id)
        if awareness is None:
            return None
        client_ids = list(awareness.states.keys())
        if not client_ids:
            return None
        return awareness.encode_awareness_update(client_ids)

    def drop(self, document_id: UUID) -> None:
        """Forget a document's awareness entirely (last connection left)."""
        self._by_document.pop(document_id, None)
