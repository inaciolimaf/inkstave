"""In-memory SyncTeX query models (spec 26).

Coordinate convention used throughout Inkstave: **PDF points (1/72 inch),
origin at the top-left of the page, y increasing downward** — which is also
SyncTeX's native vertical convention, so the frontend can map a box straight
onto a PDF.js page viewport by multiplying by ``viewport.scale``.
"""

from __future__ import annotations

from pydantic import BaseModel


class SyncTexBox(BaseModel):
    page: int  # 1-based PDF page number
    h: float  # horizontal position, PDF points, origin top-left
    v: float  # vertical position (baseline), PDF points, origin top-left
    width: float  # box width in PDF points (>= 0)
    height: float  # box height above the baseline in PDF points (>= 0)
    depth: float  # box depth below the baseline in PDF points (>= 0)


class ForwardResult(BaseModel):
    """code -> pdf: one source line may map to several PDF boxes."""

    boxes: list[SyncTexBox]


class InverseResult(BaseModel):
    """pdf -> code: the best source location for a PDF point."""

    file: str  # project-relative source path, e.g. "main.tex"
    line: int  # 1-based source line
    column: int | None = None  # 1-based column when SyncTeX provides it, else None
