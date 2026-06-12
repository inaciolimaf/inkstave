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
        inputs: dict[int, str] = {}
        magnification = 1000.0
        unit = 1.0
        x_offset = y_offset = 0.0
        version = ""
        seen_version = False

        idx = 0
        n = len(lines)
        while idx < n:
            line = lines[idx]
            if line.startswith("SyncTeX Version:"):
                version = line.split(":", 1)[1].strip()
                seen_version = True
            elif line.startswith("Input:"):
                tag_s, sep, path = line[len("Input:") :].partition(":")
                if sep:
                    try:
                        inputs[int(tag_s)] = normalise_path(path)
                    except ValueError:
                        pass
            elif line.startswith("Magnification:"):
                magnification = _field_float(line, 1000.0)
            elif line.startswith("Unit:"):
                unit = _field_float(line, 1.0)
            elif line.startswith("X Offset:"):
                x_offset = _field_float(line, 0.0)
            elif line.startswith("Y Offset:"):
                y_offset = _field_float(line, 0.0)
            elif line.startswith("Content:"):
                idx += 1
                break
            idx += 1

        if not seen_version:
            raise SyncTexParseError("missing 'SyncTeX Version:' preamble")

        scale = unit / _SP_PER_PT * (magnification / 1000.0)
        x_off_pt = x_offset * scale
        y_off_pt = y_offset * scale

        leaves_by_page: dict[int, list[_Leaf]] = {}
        page: int | None = None
        for line in lines[idx:]:
            if not line:
                continue
            head = line[0]
            if head == "{":
                try:
                    page = int(line[1:].strip() or "0")
                except ValueError:
                    page = None
                if page is not None:
                    leaves_by_page.setdefault(page, [])
                continue
            if head == "}":
                page = None
                continue
            if line.startswith("Postamble"):
                break
            if page is None:
                continue
            match = _RECORD_RE.match(line)
            if match is None:
                continue
            _type, tag_s, line_s, col_s, h_s, v_s, w_s, ht_s, d_s = match.groups()
            h_pt = int(h_s) * scale + x_off_pt
            v_pt = int(v_s) * scale + y_off_pt
            if w_s is not None:
                width = abs(int(w_s) * scale)
                height = abs(int(ht_s) * scale)
                depth = abs(int(d_s) * scale)
            else:
                width = height = depth = 0.0
            leaves_by_page[page].append(
                _Leaf(
                    page=page,
                    tag=int(tag_s),
                    line=int(line_s),
                    column=int(col_s) if col_s is not None else None,
                    h=h_pt,
                    v=v_pt,
                    width=width,
                    height=height,
                    depth=depth,
                )
            )

        forward_index: dict[tuple[str, int], list[_Leaf]] = {}
        lines_set: dict[str, set[int]] = {}
        for page_leaves in leaves_by_page.values():
            for leaf in page_leaves:
                file = inputs.get(leaf.tag)
                if file is None:
                    continue
                forward_index.setdefault((file, leaf.line), []).append(leaf)
                lines_set.setdefault(file, set()).add(leaf.line)
        lines_by_file = {file: sorted(s) for file, s in lines_set.items()}

        return cls(
            inputs=inputs,
            leaves_by_page=leaves_by_page,
            forward_index=forward_index,
            lines_by_file=lines_by_file,
            version=version,
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
