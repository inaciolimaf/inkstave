"""Unit tests for YDocument: round-trip, sync, convergence, commutativity (spec 28)."""

from __future__ import annotations

from pycrdt import Decoder

from inkstave.collab.ydocument import YDocument


def _state_vector(sv: bytes) -> dict[int, int]:
    """Decode a Yjs state vector to ``{client_id: clock}`` (the byte encoding's
    client order is not canonical, so compare logically)."""
    decoder = Decoder(sv)
    count = decoder.read_var_uint()
    return {decoder.read_var_uint(): decoder.read_var_uint() for _ in range(count)}


def test_text_round_trip_via_state() -> None:
    doc = YDocument()
    doc.replace_text("Hello")
    assert doc.text == "Hello"
    fresh = YDocument()
    fresh.apply_update(doc.get_state())
    assert fresh.text == "Hello"


def test_replace_text_is_idempotent_noop() -> None:
    doc = YDocument()
    doc.replace_text("abc")
    update = doc.replace_text("abc")  # unchanged
    assert doc.text == "abc"
    # Applying a no-op update to a peer leaves it unchanged.
    peer = YDocument()
    peer.apply_update(doc.get_state())
    peer.apply_update(update)
    assert peer.text == "abc"


def test_observer_fires_with_update_and_origin() -> None:
    doc = YDocument()
    seen: list[tuple[int, str | None]] = []
    doc.observe(lambda update, origin: seen.append((len(update), origin)))

    src = YDocument()
    src.replace_text("hi")
    doc.apply_update(src.get_state(), origin="client-7")

    assert seen
    assert seen[-1][0] > 0
    assert seen[-1][1] == "client-7"


def test_sync_protocol_converges() -> None:
    # A and B diverge from empty, then exchange diffs in both directions.
    a = YDocument()
    a.replace_text("Hello ")
    b = YDocument()
    b.apply_update(a.get_state())  # B catches up to "Hello "
    # Now both edit independently.
    a2 = YDocument()
    a2.apply_update(a.get_state())
    a2.replace_text("Hello WORLD")
    b.replace_text("Hello there")

    # Exchange Step1(state vector) -> Step2(diff) both ways.
    a2.apply_update(b.diff(a2.get_state_vector()))
    b.apply_update(a2.diff(b.get_state_vector()))

    assert a2.text == b.text
    assert _state_vector(a2.get_state_vector()) == _state_vector(b.get_state_vector())


def test_concurrent_inserts_commute() -> None:
    base = YDocument()
    base.replace_text("AB")
    base_sv = base.get_state_vector()

    d1 = YDocument()
    d1.apply_update(base.get_state())
    d1._text.insert(0, "X")  # type: ignore[attr-defined]
    u1 = d1.diff(base_sv)

    d2 = YDocument()
    d2.apply_update(base.get_state())
    d2._text.insert(0, "Y")  # type: ignore[attr-defined]
    u2 = d2.diff(base_sv)

    left = YDocument()
    left.apply_update(base.get_state())
    left.apply_update(u1)
    left.apply_update(u2)

    right = YDocument()
    right.apply_update(base.get_state())
    right.apply_update(u2)
    right.apply_update(u1)

    assert left.text == right.text  # CRDT commutativity
