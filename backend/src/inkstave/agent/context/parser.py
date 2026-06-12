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


def _extract_title(code: str, pos: int) -> str | None:
    """From `pos`, skip whitespace + an optional [..] arg, then read the {title}."""
    n = len(code)
    while pos < n and code[pos] in " \t":
        pos += 1
    if pos < n and code[pos] == "[":
        depth = 0
        while pos < n:
            if code[pos] == "[":
                depth += 1
            elif code[pos] == "]":
                depth -= 1
                if depth == 0:
                    pos += 1
                    break
            pos += 1
    while pos < n and code[pos] in " \t":
        pos += 1
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


def parse_latex_structure(
    text: str, file_path: str, extra_commands: Sequence[str] = ()
) -> list[StructureNode]:
    lines = text.split("\n")
    line_starts: list[int] = []
    offset = 0
    for line in lines:
        line_starts.append(offset)
        offset += len(line) + 1
    total_chars = len(text)
    total_lines = len(lines)
    extra_levels = {name: 1 for name in extra_commands}

    secs: list[_Sec] = []
    envs: list[StructureNode] = []
    inputs: list[StructureNode] = []
    env_stack: list[StructureNode] = []
    verbatim_stack: list[str] = []
    body_start_line: int | None = None

    def char_at(line_idx: int, col: int) -> int:
        return line_starts[line_idx] + col

    for i, raw in enumerate(lines):
        line_no = i + 1

        if verbatim_stack:
            # Verbatim content is opaque: do NOT strip comments here, or a literal '%'
            # before the closing tag would hide \end{verbatim} and swallow the rest of
            # the file. Scan the raw line for the matching \end only.
            m = _END_RE.search(raw)
            if m and m.group(1).strip() == verbatim_stack[-1]:
                verbatim_stack.pop()
                if env_stack and env_stack[-1].command == m.group(1).strip():
                    env_stack[-1].end_line = line_no
                    env_stack[-1].end_char = char_at(i, m.end()) - 1
                    env_stack.pop()
            continue

        code = _strip_comment(raw)
        for tok in _TOKEN_RE.finditer(code):
            piece = tok.group(0)
            start_char = char_at(i, tok.start())

            sec_m = _SECTION_RE.match(piece)
            if sec_m:
                name = sec_m.group(1)
                level = SECTION_LEVELS.get(name, extra_levels.get(name, 1))
                title = _extract_title(code, tok.end())
                secs.append(_Sec(name, level, title, None, line_no, start_char))
                continue

            begin_m = _BEGIN_RE.match(piece)
            if begin_m:
                env = begin_m.group(1).strip()
                if env == "document":
                    body_start_line = line_no
                    continue
                if env in VERBATIM_ENVS or env in NOTABLE_ENVS:
                    node = StructureNode(
                        kind=StructureKind.ENVIRONMENT,
                        command=env,
                        file_path=file_path,
                        start_line=line_no,
                        end_line=line_no,
                        start_char=start_char,
                        end_char=start_char,
                    )
                    env_stack.append(node)
                    envs.append(node)
                    if env in VERBATIM_ENVS:
                        verbatim_stack.append(env)
                continue

            end_m = _END_RE.match(piece)
            if end_m:
                env = end_m.group(1).strip()
                for k in range(len(env_stack) - 1, -1, -1):
                    if env_stack[k].command == env:
                        env_stack[k].end_line = line_no
                        env_stack[k].end_char = char_at(i, tok.end()) - 1
                        del env_stack[k]
                        break
                continue

            input_m = _INPUT_RE.match(piece)
            if input_m:
                inputs.append(
                    StructureNode(
                        kind=StructureKind.INPUT,
                        command=input_m.group(1),
                        title=input_m.group(2).strip(),
                        file_path=file_path,
                        start_line=line_no,
                        end_line=line_no,
                        start_char=start_char,
                        end_char=char_at(i, tok.end()) - 1,
                    )
                )
                continue

            label_m = _LABEL_RE.match(piece)
            if label_m and secs:
                # Attach a label to the nearest preceding heading on this line, else the last one.
                target = secs[-1]
                if target.label is None:
                    target.label = label_m.group(1).strip()

    # Section ranges: extend to just before the next sibling-or-higher heading.
    for idx, sec in enumerate(secs):
        nxt = next((s for s in secs[idx + 1 :] if s.level <= sec.level), None)
        if nxt is not None:
            sec.end_line = nxt.line - 1
            sec.end_char = nxt.char - 1
        else:
            sec.end_line = total_lines
            sec.end_char = max(0, total_chars - 1)

    return _assemble(file_path, lines, secs, envs, inputs, body_start_line)


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


def _assemble(
    file_path: str,
    lines: list[str],
    secs: list[_Sec],
    envs: list[StructureNode],
    inputs: list[StructureNode],
    body_start_line: int | None,
) -> list[StructureNode]:
    top: list[StructureNode] = []

    if body_start_line and body_start_line > 1:
        top.append(
            StructureNode(
                kind=StructureKind.PREAMBLE,
                command="preamble",
                file_path=file_path,
                start_line=1,
                end_line=body_start_line - 1,
                start_char=0,
                end_char=max(0, sum(len(line) + 1 for line in lines[: body_start_line - 1]) - 1),
            )
        )

    # Attach environments + inputs to the deepest section that contains them.
    def owner(node: StructureNode) -> _Sec | None:
        best: _Sec | None = None
        for sec in secs:
            if sec.line <= node.start_line <= sec.end_line:
                if best is None or sec.line > best.line:
                    best = sec
        return best

    for node in [*envs, *inputs]:
        host = owner(node)
        if host is not None:
            host.children.append(node)
        else:
            top.append(node)

    # Nest sections by level.
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

    # Order top-level + children by start_line for stable output.
    def sort_tree(items: list[StructureNode]) -> None:
        items.sort(key=lambda n: n.start_line)
        for it in items:
            sort_tree(it.children)

    sort_tree(top)
    return top
