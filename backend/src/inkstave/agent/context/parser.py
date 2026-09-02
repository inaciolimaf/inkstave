"""Lightweight LaTeX structural scanner (spec 48). Independent implementation.

A single linear, line-by-line scan that maps sectioning commands, notable
environments, and \\input-family references to file line/char ranges. It is *not* a
LaTeX parser/compiler — it never expands macros and never raises on malformed input.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from inkstave.agent.context.models import (
    NOTABLE_ENVS,
    SECTION_LEVELS,
    VERBATIM_ENVS,
    StructureKind,
    StructureNode,
)

_SECTION_RE = re.compile(
    r"\\(part|chapter|section|subsection|subsubsection|paragraph|subparagraph)(\*)?"
)
_BEGIN_RE = re.compile(r"\\begin\s*\{([^}]*)\}")
_END_RE = re.compile(r"\\end\s*\{([^}]*)\}")
_INPUT_RE = re.compile(r"\\(input|include|subfile)\s*\{([^}]*)\}")
_LABEL_RE = re.compile(r"\\label\s*\{([^}]*)\}")
_TOKEN_RE = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?"
    r"|\\begin\s*\{[^}]*\}"
    r"|\\end\s*\{[^}]*\}"
    r"|\\(?:input|include|subfile)\s*\{[^}]*\}"
    r"|\\label\s*\{[^}]*\}"
)


def _strip_comment(line: str) -> str:
    """Truncate a line at its first unescaped percent sign."""
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "%":
            return line[:i]
        i += 1
    return line


def _extract_braces(s: str, start: int) -> tuple[str | None, int]:
    """If s[start] is '{', return (balanced content, index after '}'); else (None, start)."""
    if start >= len(s) or s[start] != "{":
        return None, start
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1 : i], i + 1
    return s[start + 1 :], len(s)  # unbalanced → best-effort to EOL


def _skip_spaces(code: str, pos: int) -> int:
    """Advance past horizontal whitespace."""
    while pos < len(code) and code[pos] in " \t":
        pos += 1
    return pos


def _skip_optional_arg(code: str, pos: int) -> int:
    """Advance past a balanced ``[...]`` optional argument, if one starts at `pos`."""
    if pos >= len(code) or code[pos] != "[":
        return pos
    depth = 0
    while pos < len(code):
        if code[pos] == "[":
            depth += 1
        elif code[pos] == "]":
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return pos


def _extract_title(code: str, pos: int) -> str | None:
    """From `pos`, skip whitespace + an optional [..] arg, then read the {title}."""
    pos = _skip_spaces(code, _skip_optional_arg(code, _skip_spaces(code, pos)))
    title, _ = _extract_braces(code, pos)
    return title.strip() if title is not None else None


@dataclass
class _Sec:
    name: str
    level: int
    title: str | None
    label: str | None
    line: int
    char: int
    end_line: int = 0
    end_char: int = 0
    children: list[StructureNode] = field(default_factory=list)


@dataclass
class _Scan:
    """Mutable state of one linear pass over a file.

    Each token kind has its own small handler; `token()` is the only dispatcher,
    so adding a construct never grows the scan loop itself.
    """

    file_path: str
    line_starts: list[int]
    extra_levels: dict[str, int]
    secs: list[_Sec] = field(default_factory=list)
    envs: list[StructureNode] = field(default_factory=list)
    inputs: list[StructureNode] = field(default_factory=list)
    env_stack: list[StructureNode] = field(default_factory=list)
    verbatim_stack: list[str] = field(default_factory=list)
    body_start_line: int | None = None

    def char_at(self, line_idx: int, col: int) -> int:
        return self.line_starts[line_idx] + col

    def close_verbatim(self, line_idx: int, raw: str, line_no: int) -> None:
        """Inside a verbatim environment only its own ``\\end`` is meaningful.

        Verbatim content is opaque: do NOT strip comments here, or a literal '%'
        before the closing tag would hide \\end{verbatim} and swallow the rest of
        the file. Scan the raw line for the matching \\end only.
        """
        match = _END_RE.search(raw)
        if match is None or match.group(1).strip() != self.verbatim_stack[-1]:
            return
        self.verbatim_stack.pop()
        if self.env_stack and self.env_stack[-1].command == match.group(1).strip():
            self.env_stack[-1].end_line = line_no
            self.env_stack[-1].end_char = self.char_at(line_idx, match.end()) - 1
            self.env_stack.pop()

    def token(self, code: str, tok: re.Match[str], line_idx: int, line_no: int) -> None:
        """Route one matched token to the handler for its kind."""
        piece = tok.group(0)
        start_char = self.char_at(line_idx, tok.start())
        end_char = self.char_at(line_idx, tok.end()) - 1

        sec_m = _SECTION_RE.match(piece)
        if sec_m:
            self._section(sec_m.group(1), code, tok.end(), line_no, start_char)
            return
        begin_m = _BEGIN_RE.match(piece)
        if begin_m:
            self._begin(begin_m.group(1).strip(), line_no, start_char)
            return
        end_m = _END_RE.match(piece)
        if end_m:
            self._end(end_m.group(1).strip(), line_no, end_char)
            return
        input_m = _INPUT_RE.match(piece)
        if input_m:
            self._input(input_m, line_no, start_char, end_char)
            return
        label_m = _LABEL_RE.match(piece)
        if label_m:
            self._label(label_m.group(1).strip())

    def _section(self, name: str, code: str, after: int, line_no: int, start_char: int) -> None:
        level = SECTION_LEVELS.get(name, self.extra_levels.get(name, 1))
        title = _extract_title(code, after)
        self.secs.append(_Sec(name, level, title, None, line_no, start_char))

    def _begin(self, env: str, line_no: int, start_char: int) -> None:
        if env == "document":
            self.body_start_line = line_no
            return
        if env not in VERBATIM_ENVS and env not in NOTABLE_ENVS:
            return
        node = StructureNode(
            kind=StructureKind.ENVIRONMENT,
            command=env,
            file_path=self.file_path,
            start_line=line_no,
            end_line=line_no,
            start_char=start_char,
            end_char=start_char,
        )
        self.env_stack.append(node)
        self.envs.append(node)
        if env in VERBATIM_ENVS:
            self.verbatim_stack.append(env)

    def _end(self, env: str, line_no: int, end_char: int) -> None:
        """Close the innermost open environment with this name."""
        for k in range(len(self.env_stack) - 1, -1, -1):
            if self.env_stack[k].command == env:
                self.env_stack[k].end_line = line_no
                self.env_stack[k].end_char = end_char
                del self.env_stack[k]
                break

    def _input(self, match: re.Match[str], line_no: int, start_char: int, end_char: int) -> None:
        self.inputs.append(
            StructureNode(
                kind=StructureKind.INPUT,
                command=match.group(1),
                title=match.group(2).strip(),
                file_path=self.file_path,
                start_line=line_no,
                end_line=line_no,
                start_char=start_char,
                end_char=end_char,
            )
        )

    def _label(self, label: str) -> None:
        """Attach the label to the nearest preceding heading, if it has none yet."""
        if self.secs and self.secs[-1].label is None:
            self.secs[-1].label = label


def _line_starts(lines: list[str]) -> list[int]:
    """Character offset at which each line begins."""
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1
    return starts


def _close_section_ranges(secs: list[_Sec], total_lines: int, total_chars: int) -> None:
    """Extend each heading's range to just before the next sibling-or-higher heading."""
    for idx, sec in enumerate(secs):
        nxt = next((s for s in secs[idx + 1 :] if s.level <= sec.level), None)
        if nxt is not None:
            sec.end_line = nxt.line - 1
            sec.end_char = nxt.char - 1
        else:
            sec.end_line = total_lines
            sec.end_char = max(0, total_chars - 1)


def parse_latex_structure(
    text: str, file_path: str, extra_commands: Sequence[str] = ()
) -> list[StructureNode]:
    lines = text.split("\n")
    scan = _Scan(file_path, _line_starts(lines), {name: 1 for name in extra_commands})

    for line_idx, raw in enumerate(lines):
        line_no = line_idx + 1
        if scan.verbatim_stack:
            scan.close_verbatim(line_idx, raw, line_no)
            continue
        code = _strip_comment(raw)
        for tok in _TOKEN_RE.finditer(code):
            scan.token(code, tok, line_idx, line_no)

    _close_section_ranges(scan.secs, len(lines), len(text))
    return _assemble(file_path, lines, scan.secs, scan.envs, scan.inputs, scan.body_start_line)


def _to_node(sec: _Sec, file_path: str) -> StructureNode:
    return StructureNode(
        kind=StructureKind.SECTIONING,
        command=sec.name,
        level=sec.level,
        title=sec.title,
        label=sec.label,
        file_path=file_path,
        start_line=sec.line,
        end_line=sec.end_line,
        start_char=sec.char,
        end_char=sec.end_char,
        children=sec.children,
    )


def _preamble_node(
    file_path: str, lines: list[str], body_start_line: int | None
) -> StructureNode | None:
    """Everything before ``\\begin{document}``, or ``None`` when there is no preamble."""
    if not body_start_line or body_start_line <= 1:
        return None
    span = sum(len(line) + 1 for line in lines[: body_start_line - 1])
    return StructureNode(
        kind=StructureKind.PREAMBLE,
        command="preamble",
        file_path=file_path,
        start_line=1,
        end_line=body_start_line - 1,
        start_char=0,
        end_char=max(0, span - 1),
    )


def _owner(secs: list[_Sec], node: StructureNode) -> _Sec | None:
    """The deepest section whose range contains `node`, if any."""
    best: _Sec | None = None
    for sec in secs:
        contains = sec.line <= node.start_line <= sec.end_line
        if contains and (best is None or sec.line > best.line):
            best = sec
    return best


def _nest_sections(secs: list[_Sec], file_path: str, top: list[StructureNode]) -> None:
    """Nest headings by level; roots are appended to `top`."""
    stack: list[_Sec] = []
    nodes_by_sec: dict[int, StructureNode] = {}
    for sec in secs:
        while stack and stack[-1].level >= sec.level:
            stack.pop()
        node = _to_node(sec, file_path)
        nodes_by_sec[id(sec)] = node
        if stack:
            nodes_by_sec[id(stack[-1])].children.append(node)
        else:
            top.append(node)
        stack.append(sec)


def _sort_tree(items: list[StructureNode]) -> None:
    """Order each level by start_line for stable output."""
    items.sort(key=lambda n: n.start_line)
    for item in items:
        _sort_tree(item.children)


def _assemble(
    file_path: str,
    lines: list[str],
    secs: list[_Sec],
    envs: list[StructureNode],
    inputs: list[StructureNode],
    body_start_line: int | None,
) -> list[StructureNode]:
    top: list[StructureNode] = []
    preamble = _preamble_node(file_path, lines, body_start_line)
    if preamble is not None:
        top.append(preamble)

    # Attach environments + inputs to the deepest section that contains them.
    for node in [*envs, *inputs]:
        host = _owner(secs, node)
        if host is not None:
            host.children.append(node)
        else:
            top.append(node)

    _nest_sections(secs, file_path, top)
    _sort_tree(top)
    return top
