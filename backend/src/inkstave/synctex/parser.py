"""Independent SyncTeX parser + query index (spec 26).

Tectonic emits a gzip-compressed ``.synctex.gz`` text file. This module parses
that format directly (no shelling out to the ``synctex`` binary, no Overleaf
code) into an in-memory index answering **forward** (file+line -> PDF boxes) and
**inverse** (page+point -> file+line) queries.

## File format (the parts we use)

Preamble (one field per line)::

    SyncTeX Version:1
    Input:<tag>:<source path>     # integer tag -> source file
    Magnification:<int>           # default 1000 (== 1.0x)
    Unit:<int>                    # default 1
    X Offset:<int>                # default 0
    Y Offset:<int>                # default 0
    Content:

Content section — one record per line, grouped by sheet (``{<page>`` … ``}``)::

    [ / ]   vbox open / close
    ( / )   hbox open / close
    h v x k g $   leaf nodes (kern/glue/math/void boxes)

A data-bearing record is ``<type><tag>,<line>[,<col>]:<h>,<v>[:<W>,<H>,<D>]``
with all coordinates in scaled points (sp).

## Coordinate conversion

``pt = raw * unit / 65536 * (magnification / 1000)`` plus the (X,Y) offsets,
giving PDF points with a top-left origin (SyncTeX's native vertical sense). The
two queries and the frontend all use this one convention; see
``docs/adr/0026-synctex.md``.
"""

from __future__ import annotations

import contextlib
import gzip
import os
import posixpath
import re
from bisect import bisect_left
from dataclasses import dataclass, field

from inkstave.synctex.models import ForwardResult, InverseResult, SyncTexBox

_SP_PER_PT = 65536.0

# <type><tag>,<line>[,<column>]:<h>,<v>[:<W>,<H>,<D>] — anchored at the line start;
# trailing data (e.g. a kern's single width value) is intentionally not captured.
_RECORD_RE = re.compile(
    r"^([\[(hvxkg$])(\d+),(\d+)(?:,(\d+))?:(-?\d+),(-?\d+)(?::(-?\d+),(-?\d+),(-?\d+))?"
)


class SyncTexParseError(ValueError):
    """Raised only when the SyncTeX preamble itself cannot be read."""


def normalise_path(path: str) -> str:
    """Project-relative normalisation: strip leading ``./`` and collapse ``..``."""
    p = path.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return posixpath.normpath(p)


def _field_float(line: str, default: float) -> float:
    try:
        return float(line.split(":", 1)[1].strip())
    except (IndexError, ValueError):
        return default


@dataclass(slots=True)
class _Leaf:
    page: int
    tag: int
    line: int
    column: int | None
    h: float
    v: float
    width: float
    height: float
    depth: float

    def contains(self, h: float, v: float) -> bool:
        return (self.h <= h <= self.h + self.width) and (
            self.v - self.height <= v <= self.v + self.depth
        )

    @property
    def area(self) -> float:
        return self.width * (self.height + self.depth)


# Preamble fields that are plain floats: prefix -> (attribute, default).
_FLOAT_FIELDS = {
    "Magnification:": ("magnification", 1000.0),
    "Unit:": ("unit", 1.0),
    "X Offset:": ("x_offset", 0.0),
    "Y Offset:": ("y_offset", 0.0),
}


@dataclass(slots=True)
class _Preamble:
    """Header fields, already converted, plus where the content section starts."""

    inputs: dict[int, str]
    scale: float
    x_off_pt: float
    y_off_pt: float
    version: str
    content_at: int


@dataclass
class _Header:
    """Accumulates preamble lines as they are seen; unknown lines are ignored."""

    inputs: dict[int, str] = field(default_factory=dict)
    magnification: float = 1000.0
    unit: float = 1.0
    x_offset: float = 0.0
    y_offset: float = 0.0
    version: str | None = None

    def read(self, line: str) -> None:
        if line.startswith("SyncTeX Version:"):
            self.version = line.split(":", 1)[1].strip()
            return
        if line.startswith("Input:"):
            self._read_input(line)
            return
        for prefix, (attr, default) in _FLOAT_FIELDS.items():
            if line.startswith(prefix):
                setattr(self, attr, _field_float(line, default))
                return

    def _read_input(self, line: str) -> None:
        """Record one ``Input:<tag>:<path>`` mapping; a malformed tag is dropped."""
        tag_s, sep, path = line[len("Input:") :].partition(":")
        if sep:
            with contextlib.suppress(ValueError):
                self.inputs[int(tag_s)] = normalise_path(path)


def _parse_preamble(lines: list[str]) -> _Preamble:
    """Read the header up to ``Content:``. Raises if the version line is absent."""
    header = _Header()
    content_at = 0
    for content_at, line in enumerate(lines, start=1):  # noqa: B007 — index past `line`
        if line.startswith("Content:"):
            break
        header.read(line)

    if header.version is None:
        raise SyncTexParseError("missing 'SyncTeX Version:' preamble")

    scale = header.unit / _SP_PER_PT * (header.magnification / 1000.0)
    return _Preamble(
        inputs=header.inputs,
        scale=scale,
        x_off_pt=header.x_offset * scale,
        y_off_pt=header.y_offset * scale,
        version=header.version,
        content_at=content_at,
    )


def _sheet_number(line: str) -> int | None:
    """The page number from a ``{<page>`` sheet marker, or ``None`` if malformed."""
    try:
        return int(line[1:].strip() or "0")
    except ValueError:
        return None


def _record_leaf(line: str, page: int, pre: _Preamble) -> _Leaf | None:
    """One data-bearing record in PDF points, or ``None`` if the line is not one."""
    match = _RECORD_RE.match(line)
    if match is None:
        return None
    _type, tag_s, line_s, col_s, h_s, v_s, w_s, ht_s, d_s = match.groups()
    width = height = depth = 0.0
    if w_s is not None:
        width = abs(int(w_s) * pre.scale)
        height = abs(int(ht_s) * pre.scale)
        depth = abs(int(d_s) * pre.scale)
    return _Leaf(
        page=page,
        tag=int(tag_s),
        line=int(line_s),
        column=int(col_s) if col_s is not None else None,
        h=int(h_s) * pre.scale + pre.x_off_pt,
        v=int(v_s) * pre.scale + pre.y_off_pt,
        width=width,
        height=height,
        depth=depth,
    )


@dataclass
class _Content:
    """Leaves accumulated per sheet while walking the content section."""

    pre: _Preamble
    leaves_by_page: dict[int, list[_Leaf]] = field(default_factory=dict)
    page: int | None = None

    def open_sheet(self, line: str) -> None:
        self.page = _sheet_number(line)
        if self.page is not None:
            self.leaves_by_page.setdefault(self.page, [])

    def record(self, line: str) -> None:
        """Append one record to the open sheet; records outside a sheet are dropped."""
        if self.page is None:
            return
        leaf = _record_leaf(line, self.page, self.pre)
        if leaf is not None:
            self.leaves_by_page[self.page].append(leaf)


def _parse_content(lines: list[str], pre: _Preamble) -> dict[int, list[_Leaf]]:
    """Walk the content section, grouping leaf records by sheet."""
    content = _Content(pre)
    for line in lines:
        if not line:
            continue
        if line.startswith("Postamble"):
            break
        if line[0] == "{":
            content.open_sheet(line)
        elif line[0] == "}":
            content.page = None
        else:
            content.record(line)
    return content.leaves_by_page


def _build_index(
    inputs: dict[int, str], leaves_by_page: dict[int, list[_Leaf]]
) -> tuple[dict[tuple[str, int], list[_Leaf]], dict[str, list[int]]]:
    """Forward lookup ``(file, line) -> leaves``, plus the sorted lines per file."""
    forward_index: dict[tuple[str, int], list[_Leaf]] = {}
    lines_set: dict[str, set[int]] = {}
    for page_leaves in leaves_by_page.values():
        for leaf in page_leaves:
            file = inputs.get(leaf.tag)
            if file is None:
                continue
            forward_index.setdefault((file, leaf.line), []).append(leaf)
            lines_set.setdefault(file, set()).add(leaf.line)
    return forward_index, {file: sorted(seen) for file, seen in lines_set.items()}


@dataclass(slots=True)
class SyncTexIndex:
    inputs: dict[int, str]  # tag -> normalised source path
    leaves_by_page: dict[int, list[_Leaf]]
    forward_index: dict[tuple[str, int], list[_Leaf]]  # (file, line) -> leaves
    lines_by_file: dict[str, list[int]]  # sorted unique lines per file
    version: str = field(default="")

    # ----------------------------------------------------------------- parse #

    @classmethod
    def from_gz_bytes(cls, data: bytes) -> SyncTexIndex:
        try:
            text = gzip.decompress(data).decode("utf-8", "replace")
        except (OSError, EOFError):
            # Tolerate an already-decompressed (plain text) synctex file.
            text = data.decode("utf-8", "replace")
        return cls._parse(text)

    @classmethod
    def from_gz_path(cls, path: str | os.PathLike[str]) -> SyncTexIndex:
        with open(path, "rb") as handle:
            return cls.from_gz_bytes(handle.read())

    @classmethod
    def _parse(cls, text: str) -> SyncTexIndex:
        lines = text.splitlines()
        pre = _parse_preamble(lines)
        leaves_by_page = _parse_content(lines[pre.content_at :], pre)
        forward_index, lines_by_file = _build_index(pre.inputs, leaves_by_page)
        return cls(
            inputs=pre.inputs,
            leaves_by_page=leaves_by_page,
            forward_index=forward_index,
            lines_by_file=lines_by_file,
            version=pre.version,
        )

    # --------------------------------------------------------------- queries #

    def forward(self, file: str, line: int, column: int | None = None) -> ForwardResult:
        """code -> pdf. Boxes for the nearest indexed line ``>= line`` in that
        file, falling back to the nearest line below if none above. Empty boxes
        if the file is unknown. ``column`` is accepted but not used for matching
        (the fixtures and Tectonic group by line)."""
        key = normalise_path(file)
        available = self.lines_by_file.get(key)
        if not available:
            return ForwardResult(boxes=[])
        pos = bisect_left(available, line)
        target = available[pos] if pos < len(available) else available[-1]
        leaves = self.forward_index.get((key, target), [])
        return ForwardResult(
            boxes=[
                SyncTexBox(
                    page=leaf.page,
                    h=leaf.h,
                    v=leaf.v,
                    width=leaf.width,
                    height=leaf.height,
                    depth=leaf.depth,
                )
                for leaf in leaves
            ]
        )

    def inverse(self, page: int, h: float, v: float) -> InverseResult | None:
        """pdf -> code. The smallest box on ``page`` containing ``(h, v)``; else
        the nearest box by Euclidean distance of its reference point. ``None`` if
        the page has no records."""
        leaves = self.leaves_by_page.get(page)
        if not leaves:
            return None
        containing = [leaf for leaf in leaves if leaf.contains(h, v)]
        if containing:
            best = min(containing, key=lambda leaf: leaf.area)
        else:
            best = min(leaves, key=lambda leaf: (leaf.h - h) ** 2 + (leaf.v - v) ** 2)
        file = self.inputs.get(best.tag)
        if file is None:
            return None
        return InverseResult(file=file, line=best.line, column=best.column)
