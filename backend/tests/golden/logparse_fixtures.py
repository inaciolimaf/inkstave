"""Checked-in LaTeX-log fixtures for spec-27 tests (no real compile)."""

from __future__ import annotations

# A realistic multi-problem log: an include with an overfull box, a TeX error
# after the include closes, an undefined reference, and a generic warning.
SAMPLE_LOG = r"""This is pdfTeX, Version 3.14159265
(./main.tex
LaTeX2e <2023-11-01>
(./article.cls)
(sections/intro.tex
Overfull \hbox (12.34pt too wide) in paragraph at lines 5--7
)
! Undefined control sequence.
l.42 \badcommand

LaTeX Warning: Reference `fig:overview' undefined on input line 10.

LaTeX Warning: There were undefined references.
)
"""


def wrap79(text: str, width: int = 79) -> str:
    """Hard-wrap each line at ``width`` cols, like TeX's ``\\max_print_line``."""
    out = []
    for line in text.split("\n"):
        while len(line) > width:
            out.append(line[:width])
            line = line[width:]
        out.append(line)
    return "\n".join(out)
