"""Fuzz properties for the LaTeX log parser (spec 27) and the SyncTeX parser (spec 26). Pure.

Both parsers read output of a compile the user controls, so they must not raise on any input: the
log parser is total, and the SyncTeX parser may raise only its own ``SyncTexParseError``.
"""

from __future__ import annotations

import contextlib
import gzip

from hypothesis import given
from hypothesis import strategies as st

from inkstave.modules.compile.logparse.latex_log_parser import parse_latex_log
from inkstave.modules.compile.logparse.models import Problem, ProblemSeverity
from inkstave.modules.compile.synctex.parser import SyncTexIndex, SyncTexParseError

_LOG_FRAGMENTS = [
    "! Undefined control sequence.",
    "\nl.12 \\foo",
    "(./main.tex",
    ")",
    "(",
    "[1]",
    "Overfull \\hbox (3.0pt too wide) in paragraph at lines 5--7",
    "LaTeX Warning: Reference `x' on page 1 undefined on input line 4.",
    "! LaTeX Error: File `x.sty' not found.",
    "\n",
    "  ",
    "l.",
    "Package hyperref Warning: x.",
    "...",
    "\\",
]
_LOG = st.lists(st.one_of(st.sampled_from(_LOG_FRAGMENTS), st.text(max_size=20)), max_size=40).map("".join)

_SYNCTEX_LINES = [
    "SyncTeX Version:1",
    "Input:1:./main.tex",
    "Magnification:1000",
    "Unit:1",
    "X Offset:0",
    "Y Offset:0",
    "Content:",
    "{1",
    "}1",
    "(1,3:100,200:10,20,5",
    "h1,3:1,2",
    "[1,3:0,0",
    "]",
    "v1,4:3,4:1,1,1",
    "x1,2:1,1,1",
    "k1,2:4,5",
    "Input:2:/abs/path/x.tex",
]
_SYNCTEX = st.lists(st.one_of(st.sampled_from(_SYNCTEX_LINES), st.text(max_size=12)), max_size=40).map(
    "\n".join
)


@given(text=_LOG, root=st.sampled_from([None, "main.tex"]))
def test_the_log_parser_never_raises_and_returns_well_formed_problems(text: str, root: str | None) -> None:
    for problem in parse_latex_log(text, root_file=root):
        assert isinstance(problem, Problem)
        assert problem.severity in set(ProblemSeverity)
        assert problem.line is None or problem.line >= 1
        assert problem.rule
        assert isinstance(problem.raw, str)


@given(text=_SYNCTEX)
def test_the_synctex_parser_raises_only_its_own_error(text: str) -> None:
    try:
        index = SyncTexIndex.from_gz_bytes(gzip.compress(text.encode("utf-8")))
    except SyncTexParseError:
        return
    index.forward("./main.tex", 3)
    index.forward("main.tex", 1, 2)
    index.inverse(1, 10.0, 20.0)


@given(data=st.binary(max_size=200))
def test_the_synctex_parser_accepts_arbitrary_bytes_or_raises_its_own_error(data: bytes) -> None:
    with contextlib.suppress(SyncTexParseError):
        SyncTexIndex.from_gz_bytes(data)
