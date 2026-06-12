"""Independent LaTeX-log parser (spec 27).

A line-oriented state machine over the decoded ``output.log`` that emits ordered
:class:`Problem` records. Written from the public LaTeX-log conventions — no
Overleaf code.

## Rules (see docs/adr/0027-logparse.md)

- **De-wrap.** TeX wraps every log line at ``\\max_print_line`` (~79 cols), so a
  physical line of exactly ``wrap_width`` chars is a continuation; we rejoin such
  runs into logical lines before tokenising.
- **File stack.** ``(`` directly followed by a path-like token opens a file; ``)``
  closes one. A ``(`` not followed by a path pushes a balancing sentinel so stray
  parens in messages don't pop a real file. The current file is the top-most real
  path (falling back to ``root_file``).
- **Errors.** A ``! …`` line starts a TeX error; a later ``l.<n>`` gives the line.
  ``<file>:<line>: <msg>`` (file:line:error) is also recognised.
- **Warnings.** ``LaTeX Warning:``, ``Package/Class X Warning:``,
  ``LaTeX Font Warning:`` — a trailing ``on input line <n>.`` sets the line;
  undefined Reference/Citation get their own rule.
- **Typesetting.** ``Overfull/Underfull \\hbox|\\vbox`` with ``at lines a--b`` or
  ``detected at line n`` → severity ``info``.
"""

from __future__ import annotations

import posixpath
import re

from inkstave.logparse.models import Problem, ProblemSeverity

_FILE_PATH_RE = re.compile(r"\(([^()\s{}]*\.[A-Za-z0-9]+)")
_ERROR_RE = re.compile(r"^! (.*?)\.?$")
_LINE_MARKER_RE = re.compile(r"^l\.(\d+)\b")
_FILE_LINE_RE = re.compile(r"^(\.{0,2}/?[\w./+-]+\.[A-Za-z]+):(\d+): (.*)$")
_LATEX_WARNING_RE = re.compile(r"^LaTeX Warning: (.*)$")
_PKG_WARNING_RE = re.compile(r"^(Package|Class) (\S+) Warning: (.*)$")
_FONT_WARNING_RE = re.compile(r"^LaTeX Font Warning: (.*)$")
_BOX_RE = re.compile(r"^(Overfull|Underfull) \\([hv])box\b(.*)$")
_AT_LINES_RE = re.compile(r"at lines (\d+)--(\d+)")
_AT_LINE_RE = re.compile(r"(?:detected at|at) line (\d+)")
_INPUT_LINE_RE = re.compile(r"on input line (\d+)")
_UNDEF_REF_RE = re.compile(r"Reference\b.*\bundefined", re.IGNORECASE)
_UNDEF_CITE_RE = re.compile(r"Citation\b.*\bundefined", re.IGNORECASE)

_ERROR_BLOCK_LIMIT = 25  # lines to scan after "! " for the l.<n> marker
_PKG_CONT_LIMIT = 8  # continuation lines to fold into a package/font warning


def _normalise(path: str) -> str:
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return posixpath.normpath(p)


def _dewrap(text: str, wrap_width: int) -> list[str]:
    """Rejoin TeX's ~79-column hard wraps into logical lines."""
    physical = text.split("\n")
    if wrap_width <= 0:
        return physical
    out: list[str] = []
    buffer = ""
    for line in physical:
        buffer += line
        if len(line) == wrap_width:
            continue  # a full-width line continues on the next physical line
        out.append(buffer)
        buffer = ""
    if buffer:
        out.append(buffer)
    return out


def _current_file(stack: list[str | None], root: str | None) -> str | None:
    for entry in reversed(stack):
        if entry is not None:
            return entry
    return root


def _update_stack(stack: list[str | None], line: str) -> None:
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "(":
            match = _FILE_PATH_RE.match(line, i)
            if match:
                stack.append(_normalise(match.group(1)))
                i = match.end()
                continue
            stack.append(None)  # balancing sentinel for a non-file '('
            i += 1
        elif ch == ")":
            if stack:
                stack.pop()
            i += 1
        else:
            i += 1


def _box(line: str, file: str | None) -> Problem | None:
    match = _BOX_RE.match(line)
    if match is None:
        return None
    kind, box, _rest = match.group(1), match.group(2), match.group(3)
    rule = f"{kind.lower()}-{box}box"
    line_no: int | None = None
    end_line: int | None = None
    range_match = _AT_LINES_RE.search(line)
    if range_match:
        line_no, end_line = int(range_match.group(1)), int(range_match.group(2))
    else:
        single = _AT_LINE_RE.search(line)
        if single:
            line_no = int(single.group(1))
    return Problem(
        severity=ProblemSeverity.info,
        message=line.strip(),
        file=file,
        line=line_no,
        end_line=end_line,
        raw=line,
        rule=rule,
    )


def _warning(lines: list[str], idx: int, file: str | None) -> tuple[Problem, int] | None:
    line = lines[idx]
    pkg = _PKG_WARNING_RE.match(line)
    font = _FONT_WARNING_RE.match(line)
    latex = _LATEX_WARNING_RE.match(line)

    if pkg is not None:
        kind, name, body = pkg.group(1), pkg.group(2), pkg.group(3)
        rule = "package-warning" if kind == "Package" else "class-warning"
        prefix = f"({name})"
    elif font is not None:
        name, body, rule, prefix = "", font.group(1), "font-warning", "(Font)"
    elif latex is not None:
        body, rule, prefix = latex.group(1), "latex-warning", None
    else:
        return None

    parts = [body.strip()]
    raw = [line]
    consumed = 1
    # Fold continuation lines ("(name) …") for package/font warnings.
    if prefix is not None:
        j = idx + 1
        while j < len(lines) and consumed <= _PKG_CONT_LIMIT and lines[j].startswith(prefix):
            cont = lines[j][len(prefix) :].strip()
            if cont:
                parts.append(cont)
            raw.append(lines[j])
            j += 1
            consumed += 1

    message = " ".join(p for p in parts if p).strip()
    if _UNDEF_REF_RE.search(message):
        rule = "undefined-ref"
    elif _UNDEF_CITE_RE.search(message):
        rule = "undefined-cite"

    input_match = _INPUT_LINE_RE.search(message)
    line_no = int(input_match.group(1)) if input_match else None
    return (
        Problem(
            severity=ProblemSeverity.warning,
            message=message,
            file=file,
            line=line_no,
            end_line=None,
            raw="\n".join(raw),
            rule=rule,
        ),
        consumed,
    )


def _error(lines: list[str], idx: int, file: str | None) -> tuple[Problem, int]:
    message = _ERROR_RE.match(lines[idx]).group(1)  # type: ignore[union-attr]
    raw = [lines[idx]]
    line_no: int | None = None
    consumed = 1
    j = idx + 1
    while j < len(lines) and (j - idx) <= _ERROR_BLOCK_LIMIT:
        nxt = lines[j]
        raw.append(nxt)
        consumed += 1
        marker = _LINE_MARKER_RE.match(nxt)
        if marker is not None:
            line_no = int(marker.group(1))
            break
        if nxt.startswith("! ") or nxt == "":
            consumed -= 1  # don't swallow the next block / trailing blank
            raw.pop()
            break
        j += 1
    return (
        Problem(
            severity=ProblemSeverity.error,
            message=message.strip(),
            file=file,
            line=line_no,
            end_line=None,
            raw="\n".join(raw),
            rule="tex-error",
        ),
        consumed,
    )


def _file_line_error(line: str) -> Problem | None:
    match = _FILE_LINE_RE.match(line)
    if match is None:
        return None
    return Problem(
        severity=ProblemSeverity.error,
        message=match.group(3).strip(),
        file=_normalise(match.group(1)),
        line=int(match.group(2)),
        end_line=None,
        raw=line,
        rule="tex-error",
    )


def parse_latex_log(
    text: str, *, root_file: str | None = None, wrap_width: int = 79
) -> list[Problem]:
    """Parse LaTeX log ``text`` into ordered problems.

    Pure and total over content — never raises on weird logs; only raises
    ``ValueError`` on a ``None``/non-``str`` input. ``root_file`` seeds the file
    stack so unattributed early messages map to the main document.
    """
    if not isinstance(text, str):
        raise ValueError("parse_latex_log expects a string")

    lines = _dewrap(text, wrap_width)
    root = _normalise(root_file) if root_file else None
    stack: list[str | None] = []
    problems: list[Problem] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        current = _current_file(stack, root)
        advance = 1

        if line.startswith("! "):
            problem, advance = _error(lines, i, current)
            problems.append(problem)
        elif (file_line := _file_line_error(line)) is not None:
            problems.append(file_line)
        elif (warning := _warning(lines, i, current)) is not None:
            problems.append(warning[0])
            advance = warning[1]
        elif (box := _box(line, current)) is not None:
            problems.append(box)

        for k in range(i, min(i + advance, n)):
            _update_stack(stack, lines[k])
        i += advance

    return problems
