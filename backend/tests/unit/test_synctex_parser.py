"""Unit tests for the SyncTeX parser + query index (spec 26)."""

from __future__ import annotations

import pytest

from inkstave.synctex.parser import SyncTexIndex, SyncTexParseError, normalise_path
from tests.synctex_fixtures import MULTI_FILE, SINGLE_FILE, gz

TOL = 1.0  # ±1 pt tolerance (spec criterion 1)


def _single() -> SyncTexIndex:
    return SyncTexIndex.from_gz_bytes(gz(SINGLE_FILE))


def _multi() -> SyncTexIndex:
    return SyncTexIndex.from_gz_bytes(gz(MULTI_FILE))


# --- preamble / conversion ------------------------------------------------- #


def test_parses_preamble_and_inputs() -> None:
    index = _single()
    assert index.version == "1"
    assert index.inputs == {1: "main.tex"}


def test_normalise_path_strips_dot_slash_and_collapses() -> None:
    assert normalise_path("./main.tex") == "main.tex"
    assert normalise_path("sections/../sections/intro.tex") == "sections/intro.tex"
    assert normalise_path("./sections/intro.tex") == "sections/intro.tex"


def test_missing_preamble_raises() -> None:
    with pytest.raises(SyncTexParseError):
        SyncTexIndex.from_gz_bytes(gz("Input:1:main.tex\nContent:\n{1\n}\n"))


def test_plain_text_is_tolerated() -> None:
    # Not gzipped — the parser falls back to decoding raw bytes.
    index = SyncTexIndex.from_gz_bytes(SINGLE_FILE.encode("utf-8"))
    assert index.inputs == {1: "main.tex"}


def test_malformed_records_are_skipped() -> None:
    text = SINGLE_FILE.replace("x1,10:6553600,13107200", "garbage-not-a-record")
    index = SyncTexIndex.from_gz_bytes(gz(text))
    # Line 10 still has its hbox record; parsing did not crash.
    assert index.forward("main.tex", 10).boxes


# NOTE (spec 26 §8 placement): the ``SYNCTEX_MAX_GZ_BYTES`` size guard is *not*
# tested here. It is enforced at the **service** layer (before the parser is ever
# invoked), so its test lives where it belongs — in
# ``test_synctex_service.py::test_oversize_synctex_is_refused``. The parser
# operates on already-bounded bytes and has no size knowledge of its own.


# --- forward (code -> pdf) ------------------------------------------------- #


def test_forward_same_file_exact_line() -> None:
    result = _single().forward("main.tex", 10)
    assert result.boxes
    box = result.boxes[0]
    assert box.page == 1
    assert abs(box.v - 200.0) <= TOL
    assert abs(box.h - 100.0) <= TOL
    assert abs(box.width - 400.0) <= TOL


def test_forward_nearest_line_above() -> None:
    result = _single().forward("main.tex", 15)  # no record at 15 -> nearest >= 15 == 20
    assert result.boxes
    assert abs(result.boxes[0].v - 400.0) <= TOL


def test_forward_nearest_line_below_when_none_above() -> None:
    result = _single().forward("main.tex", 100)  # nothing >= 100 -> nearest below == 30 (page 2)
    assert result.boxes
    assert result.boxes[0].page == 2


def test_forward_unknown_file_is_empty() -> None:
    assert _single().forward("nope.tex", 1).boxes == []


# --- inverse (pdf -> code) ------------------------------------------------- #


def test_inverse_inside_box() -> None:
    result = _single().inverse(1, 150.0, 201.0)
    assert result is not None
    assert result.file == "main.tex"
    assert result.line == 10


def test_inverse_nearest_when_outside_all_boxes() -> None:
    result = _single().inverse(1, 1000.0, 1000.0)
    assert result is not None
    assert result.line == 20  # nearest reference point is line 20 @ (100,400)


def test_inverse_unknown_page_is_none() -> None:
    assert _single().inverse(99, 100.0, 200.0) is None


def test_multi_file_inverse_returns_relative_path() -> None:
    result = _multi().inverse(1, 150.0, 401.0)
    assert result is not None
    assert result.file == "sections/intro.tex"
    assert result.line == 5


# --- coordinate round-trip (criterion 9) ----------------------------------- #


def test_forward_inverse_round_trip_is_stable() -> None:
    index = _single()
    box = index.forward("main.tex", 10).boxes[0]
    back = index.inverse(box.page, box.h, box.v)
    assert back is not None
    assert back.line == 10
