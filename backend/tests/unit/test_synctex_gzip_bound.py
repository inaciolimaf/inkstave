"""The SyncTeX gzip decompression is bounded, so a small archive cannot expand without limit."""

from __future__ import annotations

import gzip

import pytest

from inkstave.modules.compile.synctex.parser import SyncTexIndex, SyncTexTooLargeError

_MIB = 1024 * 1024


def test_decompression_bomb_is_refused_once_it_passes_the_limit() -> None:
    bomb = gzip.compress(b"A" * (20 * _MIB), compresslevel=9)
    assert len(bomb) < _MIB  # a small archive that would expand to 20 MiB

    with pytest.raises(SyncTexTooLargeError):
        SyncTexIndex.from_gz_bytes(bomb, max_bytes=_MIB)


def test_plain_text_over_the_limit_is_refused() -> None:
    with pytest.raises(SyncTexTooLargeError):
        SyncTexIndex.from_gz_bytes(b"A" * (2 * _MIB), max_bytes=_MIB)


def test_a_multi_member_archive_within_the_limit_is_read_in_full() -> None:
    text = "SyncTeX Version:1\nInput:1:main.tex\nContent:\n"
    data = gzip.compress(text.encode()) + gzip.compress(b"Postamble:\n")
    index = SyncTexIndex.from_gz_bytes(data, max_bytes=_MIB)
    assert index.inputs == {1: "main.tex"}
