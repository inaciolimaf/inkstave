"""Unit tests for output classification and HTTP range parsing (spec 23)."""

from __future__ import annotations

import pytest

from inkstave.compile.outputs import ByteRange, RangeResult, classify, parse_range
from inkstave.db.models.compile_output import OutputKind


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("output.pdf", OutputKind.PDF),
        ("main.log", OutputKind.LOG),
        ("main.synctex.gz", OutputKind.SYNCTEX),
        ("main.aux", OutputKind.AUX),
        ("main.fls", OutputKind.AUX),
        ("main.fdb_latexmk", OutputKind.AUX),
        ("weird.bin", OutputKind.OTHER),
    ],
)
def test_classify(name: str, kind: OutputKind) -> None:
    assert classify(name) is kind


def test_parse_range_none_is_full() -> None:
    assert parse_range(None, 1000) is RangeResult.FULL
    assert parse_range("", 1000) is RangeResult.FULL


def test_parse_range_explicit_bounds() -> None:
    r = parse_range("bytes=0-99", 1000)
    assert isinstance(r, ByteRange)
    assert (r.start, r.end, r.length) == (0, 99, 100)


def test_parse_range_open_ended() -> None:
    r = parse_range("bytes=500-", 1000)
    assert isinstance(r, ByteRange)
    assert (r.start, r.end) == (500, 999)


def test_parse_range_suffix() -> None:
    r = parse_range("bytes=-100", 1000)
    assert isinstance(r, ByteRange)
    assert (r.start, r.end) == (900, 999)


def test_parse_range_clamps_end() -> None:
    r = parse_range("bytes=500-5000", 1000)
    assert isinstance(r, ByteRange)
    assert (r.start, r.end) == (500, 999)


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=2000-3000", "bytes=-0"])
def test_parse_range_unsatisfiable(header: str) -> None:
    assert parse_range(header, 1000) is RangeResult.UNSATISFIABLE


def test_parse_range_malformed_falls_back_to_full() -> None:
    assert parse_range("megabytes=0-1", 1000) is RangeResult.FULL


def test_parse_range_exact_last_byte() -> None:
    r = parse_range("bytes=999-999", 1000)
    assert isinstance(r, ByteRange)
    assert (r.start, r.end, r.length) == (999, 999, 1)


def test_parse_range_whole_object_explicit() -> None:
    r = parse_range("bytes=0-999", 1000)
    assert isinstance(r, ByteRange)
    assert (r.start, r.end, r.length) == (0, 999, 1000)


@pytest.mark.parametrize("header", ["bytes=0-0", "bytes=0-", "bytes=-1"])
def test_parse_range_on_zero_length_object_is_unsatisfiable(header: str) -> None:
    # Any byte range against an empty object cannot be satisfied.
    assert parse_range(header, 0) is RangeResult.UNSATISFIABLE
