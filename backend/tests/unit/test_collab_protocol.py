"""Unit tests for the y-protocols message framing (spec 28)."""

from __future__ import annotations

from inkstave.collab.protocol import (
    AwarenessMessage,
    SyncStep1,
    SyncStep2,
    SyncUpdate,
    UnknownMessage,
    encode_awareness,
    encode_sync_step1,
    encode_sync_step2,
    encode_update,
    read_message,
)


def test_sync_step1_round_trip() -> None:
    msg = read_message(encode_sync_step1(b"\x01\x02\x03"))
    assert isinstance(msg, SyncStep1)
    assert msg.state_vector == b"\x01\x02\x03"


def test_sync_step2_round_trip() -> None:
    msg = read_message(encode_sync_step2(b"update-bytes"))
    assert isinstance(msg, SyncStep2)
    assert msg.update == b"update-bytes"


def test_sync_update_round_trip() -> None:
    msg = read_message(encode_update(b"u"))
    assert isinstance(msg, SyncUpdate)
    assert msg.update == b"u"


def test_awareness_round_trip() -> None:
    msg = read_message(encode_awareness(b"awareness"))
    assert isinstance(msg, AwarenessMessage)
    assert msg.update == b"awareness"


def test_unknown_outer_tag() -> None:
    from pycrdt import write_var_uint

    assert isinstance(read_message(write_var_uint(7) + b"junk"), UnknownMessage)


def test_unknown_sync_subtype() -> None:
    from pycrdt import write_message, write_var_uint

    data = write_var_uint(0) + write_var_uint(9) + write_message(b"x")
    assert isinstance(read_message(data), UnknownMessage)


def test_malformed_does_not_raise() -> None:
    for data in (b"", b"\xff", b"\xff\xff\xff\xff"):
        assert isinstance(read_message(data), UnknownMessage)
