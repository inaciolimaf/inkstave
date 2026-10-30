"""Upload filename/extension/content-match hardening (spec 52 §5.2.5)."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")

# extension → content-types acceptable for it (a `.png` must actually sniff as PNG).
_EXTENSION_FAMILY: dict[str, set[str]] = {
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".pdf": {"application/pdf"},
}


def sanitize_filename(name: str | None) -> str:
    """Strip directory components, NUL, and unsafe chars; cap length.

    Path traversal (``../``), absolute paths, and backslash separators are removed
    by taking only the final path component; leading dots (hidden/traversal) are
    dropped. The result is never empty and is what gets stored.
    """
    candidate = (name or "").replace("\x00", "")
    candidate = candidate.replace("\\", "/").rsplit("/", 1)[-1]  # final component only
    candidate = _UNSAFE.sub("_", candidate).strip().lstrip(".")
    return candidate[:255] or "file"


def extension_of(name: str) -> str:
    return os.path.splitext(name.lower())[1]


def extension_allowed(name: str, allowed: Sequence[str]) -> bool:
    return extension_of(name) in {e.lower() for e in allowed}


def content_matches_extension(name: str, content_type: str) -> bool:
    """True when the sniffed content type is consistent with the file extension.

    Text-ish extensions (.tex/.bib/.csv/.svg/.eps/…) carry no binary signature, so
    they are accepted as-is; binary extensions must match their magic-byte family.
    """
    family = _EXTENSION_FAMILY.get(extension_of(name))
    return family is None or content_type in family
