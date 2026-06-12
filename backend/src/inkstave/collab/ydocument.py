"""YDocument: a pycrdt.Doc holding one shared text, with sync helpers (spec 28)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pycrdt import Doc, Text


class YDocument:
    """A single shared-text Yjs document (root key ``"content"``).

    Mutations and applied updates emit ``(update_bytes, origin)`` to registered
    observers so the manager can persist + relay them. The ``origin`` of the most
    recent mutation is captured around ``apply_update``/``replace_text``.
    """

    TEXT_KEY = "content"

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

    def observe(self, callback: Callable[[bytes, str | None], None]) -> None:
        self._observers.append(callback)
