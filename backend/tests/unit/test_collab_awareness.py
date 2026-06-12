"""Unit tests for the in-memory awareness registry (spec 28)."""

from __future__ import annotations

from uuid import uuid4

from pycrdt import Awareness, Doc

from inkstave.collab.awareness import AwarenessRegistry


def _client_update(state: dict[str, object]) -> tuple[int, bytes]:
    client = Awareness(Doc())
    client.set_local_state(state)
    return client.client_id, client.encode_awareness_update([client.client_id])


def test_apply_merges_and_returns_relayable_blob() -> None:
    reg = AwarenessRegistry()
    doc_id = uuid4()
    client_id, blob = _client_update({"user": "alice"})

    relay = reg.apply(doc_id, blob)
    assert relay == blob

    snapshot = reg.snapshot(doc_id)
    assert snapshot is not None and len(snapshot) > 0


def test_remove_client_emits_offline_update() -> None:
    reg = AwarenessRegistry()
    doc_id = uuid4()
    client_id, blob = _client_update({"user": "bob"})
    reg.apply(doc_id, blob)

    offline = reg.remove_client(doc_id, client_id)
    assert offline is not None
    assert offline != blob  # an offline marker, not the original presence
    # The client's live state is cleared (Yjs keeps an offline marker, not data).
    assert not reg._awareness(doc_id).states.get(client_id)


def test_snapshot_none_for_unknown_document() -> None:
    assert AwarenessRegistry().snapshot(uuid4()) is None


def test_remove_unknown_client_is_none() -> None:
    reg = AwarenessRegistry()
    doc_id = uuid4()
    assert reg.remove_client(doc_id, 12345) is None
