"""Names chosen by the import of a zip archive (specs 101, 120).

Pure helpers: the default project name, the rename of a name clash and of a
reserved device name. The import route and the job both use them, so the
name a project gets at upload is the one the job compares against.
"""

from __future__ import annotations

import os

from inkstave.modules.projects.content.uploads import sanitize_filename

MAX_NAME_LENGTH = 255
# How many ``name (n).ext`` candidates a case clash tries before the import fails.
MAX_CLASH_RENAMES = 99


def default_import_name(filename: str | None) -> str:
    """The archive's stem as a project name, or ``Imported project`` when there is none."""
    if filename:
        stem = sanitize_filename(os.path.splitext(filename)[0])
        if stem and stem != "file":
            return stem
    return "Imported project"


def numbered_name(name: str, number: int) -> str:
    """``Intro.tex`` with 2 becomes ``Intro (2).tex``; a name without a dot gets the suffix at the end."""
    stem, dot, ext = name.rpartition(".")
    if not stem:
        stem, dot, ext = name, "", ""
    suffix = f" ({number})"
    stem = stem[: MAX_NAME_LENGTH - len(suffix) - len(dot) - len(ext)]
    return f"{stem}{suffix}{dot}{ext}"


def reserved_safe_name(segment: str) -> str:
    """``con.tex`` becomes ``con_.tex``: the device stem gets an underscore, the extension stays."""
    stem, dot, rest = segment.partition(".")
    return f"{stem}_{dot}{rest}"
