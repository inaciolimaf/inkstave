"""Unit tests for the SyncTeX parser + query index (spec 26)."""

from __future__ import annotations

import pytest

from inkstave.modules.compile.synctex.parser import SyncTexIndex, SyncTexParseError, normalise_path
from tests.golden.synctex_fixtures import MULTI_FILE, SINGLE_FILE, gz

TOL = 1.0  # ±1 pt tolerance (spec criterion 1)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/tmp/inkstave-compiles/7efb79bd-e19b-4351-9576-4f8be2608f82/input/artigo.tex", "artigo.tex"),
        ("/var/x/7efb79bd-e19b-4351-9576-4f8be2608f82/input/./a/input/b.tex", "a/input/b.tex"),
        ("/work/sections/a.tex", "sections/a.tex"),
        ("./sections/a.tex", "sections/a.tex"),
        ("/usr/share/texmf/article.cls", "/usr/share/texmf/article.cls"),
    ],
)
def test_paths_become_project_relative(raw: str, expected: str) -> None:
    assert normalise_path(raw) == expected


def test_both_directions_work_on_a_compile_with_absolute_paths() -> None:
    root = "/tmp/inkstave-compiles/7efb79bd-e19b-4351-9576-4f8be2608f82/input"
    text = (
        "SyncTeX Version:1\n"
        f"Input:1:{root}/artigo.tex\n"
        "Input:2:/usr/share/texmf/article.cls\n"
        "Unit:1\nX Offset:0\nY Offset:0\nMagnification:1000\n"
        "Content:\n{1\n"
        "x2,1:0,0\n"
        "x1,7:6553600,6553600\n"
        "}1\nPostamble:\n"
    )
    index = SyncTexIndex.from_gz_bytes(gz(text))
    assert list(index.inputs.values()) == ["artigo.tex"]  # the class file is not a project file
    assert index.forward("artigo.tex", 7).boxes
    result = index.inverse(1, 0, 0)
    assert result is not None and result.file == "artigo.tex" and result.line == 7


def _single() -> SyncTexIndex:
    return SyncTexIndex.from_gz_bytes(gz(SINGLE_FILE))


def _multi() -> SyncTexIndex:
    return SyncTexIndex.from_gz_bytes(gz(MULTI_FILE))


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


def test_forward_inverse_round_trip_is_stable() -> None:
    index = _single()
    box = index.forward("main.tex", 10).boxes[0]
    back = index.inverse(box.page, box.h, box.v)
    assert back is not None
    assert back.line == 10
