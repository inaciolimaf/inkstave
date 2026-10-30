"""Decode text entries and pick the project's root document (spec 101)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkstave.modules.projects.content.uploads import extension_of

if TYPE_CHECKING:
    pass

from inkstave.modules.projects.transfer.zip_import.plan import PlannedEntry

_BOM = b"\xef\xbb\xbf"


def decode_text(raw: bytes) -> str:
    """Decode archive bytes to document text, never raising ``UnicodeDecodeError``.

    Strips a leading UTF-8 BOM, tries UTF-8 then cp1252 then latin-1 (which never
    fails), and normalises CRLF/CR line endings to ``\\n``.
    """
    if raw.startswith(_BOM):
        raw = raw[len(_BOM) :]
    text: str | None = None
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:  # pragma: no cover - latin-1 above never fails
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


_DOCUMENTCLASS = b"\\documentclass"


def detect_root_doc(
    planned: list[PlannedEntry], text_blobs: dict[tuple[str, ...], bytes]
) -> tuple[str, ...] | None:
    """Pick the main ``.tex``.

    First a ``.tex`` whose bytes contain ``\\documentclass`` (shallowest path
    wins; ties broken by a ``main.tex`` basename then lexicographically); else a
    top-level ``main.tex``; else the only ``.tex``; else ``None``.
    """
    tex = [e for e in planned if extension_of(e.parts[-1]) == ".tex"]
    if not tex:
        return None

    def sort_key(e: PlannedEntry) -> tuple[int, int, str]:
        return (len(e.parts), 0 if e.parts[-1].lower() == "main.tex" else 1, "/".join(e.parts))

    with_class = [e for e in tex if _DOCUMENTCLASS in text_blobs.get(e.parts, b"")]
    if with_class:
        return min(with_class, key=sort_key).parts

    top_main = [e for e in tex if len(e.parts) == 1 and e.parts[-1].lower() == "main.tex"]
    if top_main:
        return top_main[0].parts

    if len(tex) == 1:
        return tex[0].parts
    return None
