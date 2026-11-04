"""YDocument: a pycrdt.Doc holding one shared text, with sync helpers (spec 28)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pycrdt import Doc, Map, Text


class YDocument:
    """A single shared-text Yjs document (root key ``"content"``).

    Mutations and applied updates emit ``(update_bytes, origin)`` to registered
    observers so the manager can persist + relay them. The ``origin`` of the most
    recent mutation is captured around ``apply_update``/``replace_text``.

    The document also carries the suggestions map (spec 119, root key ``"suggestions"``). The server
    never writes it: it stores and relays it with the rest of the state, and only reads it in tests.
    """

    TEXT_KEY = "content"
    SUGGESTIONS_KEY = "suggestions"

    def __init__(self, doc: Doc[Any] | None = None) -> None:
        self._doc: Doc[Any] = doc or Doc()
        self._text: Text = self._doc.get(self.TEXT_KEY, type=Text)
        self._observers: list[Callable[[bytes, str | None], None]] = []
        self._origin: str | None = None
        self._doc.observe(self._on_transaction)

    def _on_transaction(self, event: object) -> None:
        update = getattr(event, "update", None)
        if not update:
            return
        for callback in self._observers:
            callback(update, self._origin)

    @property
    def text(self) -> str:
        return str(self._text)

    def suggestions(self) -> dict[str, Any]:
        """The suggestions map as plain data, keyed by suggestion id (spec 119)."""
        return self._doc.get(self.SUGGESTIONS_KEY, type=Map).to_py() or {}

    def get_state(self) -> bytes:
        """Full state update encoding the whole document (snapshot)."""
        return self._doc.get_update()

    def get_state_vector(self) -> bytes:
        return self._doc.get_state()

    def diff(self, remote_state_vector: bytes) -> bytes:
        """The update a peer with ``remote_state_vector`` is missing (SYNC_STEP_2)."""
        return self._doc.get_update(remote_state_vector)

    def apply_update(self, update: bytes, origin: str | None = None) -> None:
        self._origin = origin
        try:
            self._doc.apply_update(update)
        finally:
            self._origin = None

    def replace_text(self, new_text: str) -> bytes:
        """Set the shared text to ``new_text`` (initial load from spec-13).

        Returns the produced update. Diffs against the current state so an
        identical text is a no-op and only the changed range is emitted.
        """
        before = self._doc.get_state()
        with self._doc.transaction():
            current = str(self._text)
            if current != new_text:
                if current:
                    self._text.clear()
                if new_text:
                    self._text.insert(0, new_text)
        return self._doc.get_update(before)

    def apply_edits(self, edits: Sequence[tuple[int, int, str]]) -> bytes:
        """Apply ``(start, end, text)`` character edits to the shared text in one transaction (spec 121).

        Offsets are character positions in the text as it is before the call. pycrdt counts UTF-8
        bytes, so each position is converted against that text, and the edits run from the end so
        an earlier position is not shifted by a later one. Returns the produced update.
        """
        before = self._doc.get_state()
        current = str(self._text)
        with self._doc.transaction():
            for start, end, replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
                byte_start = len(current[:start].encode("utf-8"))
                byte_end = len(current[:end].encode("utf-8"))
                if byte_end > byte_start:
                    del self._text[byte_start:byte_end]
                if replacement:
                    self._text.insert(byte_start, replacement)
        return self._doc.get_update(before)

    def observe(self, callback: Callable[[bytes, str | None], None]) -> None:
        self._observers.append(callback)
