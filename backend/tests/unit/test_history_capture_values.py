"""Unit tests for the values between buffering and writing a history update (spec 36). Pure: no database."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.history.versions.capture_values import Pending, Replica, UpdateEntry, doc_from

if TYPE_CHECKING:
    from inkstave.modules.history.models import HistoryChunk


def _state(text: str) -> bytes:
    doc = YDocument()
    doc.replace_text(text)
    return doc.get_state()


def test_a_replica_with_no_live_state_never_drifts() -> None:
    replica = Replica(doc=doc_from(_state("history text")), live=None)
    assert replica.drifted_from_live() is False


def test_a_replica_that_is_the_live_state_never_drifts() -> None:
    # The document's first chunk: the replica came from the live state, so it cannot disagree with it.
    replica = Replica(doc=doc_from(_state("live text")), live=_state("other text"), from_live=True)
    assert replica.drifted_from_live() is False


def test_a_rebuilt_replica_with_the_live_text_has_not_drifted() -> None:
    replica = Replica(doc=doc_from(_state("same")), live=_state("same"))
    assert replica.drifted_from_live() is False


def test_a_rebuilt_replica_that_disagrees_with_the_live_text_has_drifted() -> None:
    replica = Replica(doc=doc_from(_state("from history")), live=_state("live now"))
    assert replica.drifted_from_live() is True


def test_update_entry_of_copies_every_field_of_the_pending_update() -> None:
    project_id, doc_id, author_id = uuid4(), uuid4(), uuid4()
    at = datetime(2026, 11, 1, 12, 30, tzinfo=UTC)
    pending = Pending(
        merged=b"merged-update",
        op_count=7,
        author_id=author_id,
        at=at,
        project_id=project_id,
        origin="git-push",
    )
    chunk = cast("HistoryChunk", object())  # `of` only stores the chunk; no model behaviour is involved
    entry = UpdateEntry.of(chunk, doc_id, 4, pending)
    assert entry == UpdateEntry(
        chunk=chunk,
        project_id=project_id,
        doc_id=doc_id,
        version=4,
        payload=b"merged-update",
        op_count=7,
        author_id=author_id,
        at=at,
        origin="git-push",
    )


def test_update_entry_of_keeps_an_anonymous_editors_update_without_an_origin() -> None:
    pending = Pending(
        merged=b"u", op_count=1, author_id=None, at=datetime(2026, 1, 1, tzinfo=UTC), project_id=uuid4()
    )
    entry = UpdateEntry.of(cast("HistoryChunk", object()), uuid4(), 1, pending)
    assert entry.author_id is None
    assert entry.origin is None
