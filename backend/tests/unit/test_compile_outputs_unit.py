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
