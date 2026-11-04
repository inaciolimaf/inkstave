"""Validate an archive's central directory without extracting a byte (spec 101)."""

from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from inkstave.core.errors import AppError
from inkstave.modules.projects.content.uploads import extension_of
from inkstave.modules.projects.transfer.names import reserved_safe_name
from inkstave.modules.projects.tree.safe_path import InvalidNameError, is_reserved_name, validate_name_segment

if TYPE_CHECKING:
    from inkstave.core.config.settings import Settings

# Extensions whose contents are stored as document text (spec 13) rather than as
# binary blobs (spec 14). Lower-cased, including the leading dot. This set is the
# authority for "text"; everything else in ``allowed_extensions`` is binary.
TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".tex",
        ".bib",
        ".txt",
        ".cls",
        ".sty",
        ".bst",
        ".md",
        ".markdown",
        ".csv",
        ".tsv",
        ".json",
        ".yml",
        ".yaml",
        ".xml",
        ".svg",
        ".tikz",
        ".latex",
        ".ltx",
        ".def",
        ".cfg",
        ".gitignore",
        ".bbx",
        ".cbx",
    }
)


# Text files that carry no extension, kept as documents only for an Overleaf template (spec 120).
_TEMPLATE_TEXT_NAMES = frozenset({"latexmkrc", ".latexmkrc"})


@dataclass(frozen=True)
class ImportLimits:
    max_zip_bytes: int
    max_uncompressed_bytes: int
    max_file_bytes: int
    max_entries: int
    allowed_extensions: frozenset[str]  # lower-cased, incl. dot
    # Overleaf template import (spec 120): reserved names are renamed, not rejected, and latexmkrc is text.
    template: bool = False


def limits_from_settings(settings: Settings, *, template: bool = False) -> ImportLimits:
    return ImportLimits(
        max_zip_bytes=settings.import_max_zip_bytes,
        max_uncompressed_bytes=settings.import_max_uncompressed_bytes,
        max_file_bytes=settings.import_max_file_bytes,
        max_entries=settings.import_max_entries,
        allowed_extensions=frozenset(e.lower() for e in settings.import_allowed_extensions),
        template=template,
    )


@dataclass(frozen=True)
class PlannedEntry:
    zip_name: str  # the original archive member name (for re-reading bytes)
    parts: tuple[str, ...]  # validated, traversal-free path segments
    is_dir: bool
    uncompressed_size: int  # declared, from the central directory
    classification: Literal["text", "binary"]


@dataclass(frozen=True)
class ImportPlan:
    entries: list[PlannedEntry]  # importable (kept) leaf entries
    skipped: int  # disallowed-extension entries (counted toward total, not imported)
    template: bool = False  # the archive is an Overleaf template (spec 120)


@dataclass
class ImportOutcome:
    folders_created: int = 0
    docs_created: int = 0
    files_created: int = 0
    skipped: int = 0  # entries skipped at reconstruction (oversize / bad MIME / conflict)
    root_doc_entity_id: UUID | None = None
    root_doc_path: tuple[str, ...] | None = None


class ZipImportError(AppError):
    """A rejected archive. 422 family; ``error_type`` set per subclass."""

    status_code = 422
    error_type = "invalid_zip"


class ZipSlipError(ZipImportError):
    error_type = "zip_slip"


class ZipBombError(ZipImportError):
    error_type = "zip_too_large"


class ZipEntryCountError(ZipImportError):
    error_type = "zip_too_many_entries"


class InvalidZipError(ZipImportError):
    error_type = "invalid_zip"


class SymlinkEntryError(ZipImportError):
    error_type = "zip_symlink"


class EmptyArchiveError(ZipImportError):
    error_type = "zip_empty"


# Ignorable junk: first path segment / basename matches are dropped silently
# (not imported, not counted as skipped).
_IGNORED_FIRST_SEGMENTS = {"__MACOSX", ".git"}
_IGNORED_BASENAMES = {".DS_Store"}


def _classify(name: str, limits: ImportLimits) -> Literal["text", "binary"] | None:
    base = name.lower()
    ext = extension_of(name)
    if ext in TEXT_EXTENSIONS or base in TEXT_EXTENSIONS:
        return "text"
    if limits.template and base in _TEMPLATE_TEXT_NAMES:
        return "text"
    if ext in limits.allowed_extensions:
        return "binary"
    return None


def _checked_segment(seg: str, template: bool) -> str:
    """One path segment as stored. A reserved device name is renamed for a template (spec 120)."""
    if seg in (".", ".."):
        raise ZipSlipError("Archive entry contains a path-traversal segment.")
    try:
        return validate_name_segment(seg)
    except InvalidNameError as exc:
        if template and is_reserved_name(seg):
            return _renamed_segment(seg)
        raise ZipSlipError(f"Archive entry has an unsafe path segment: {seg!r}") from exc


def _renamed_segment(seg: str) -> str:
    try:
        return validate_name_segment(reserved_safe_name(seg))
    except InvalidNameError as exc:
        raise ZipSlipError(f"Archive entry has an unsafe path segment: {seg!r}") from exc


def _safe_parts(raw: str, template: bool = False) -> tuple[str, ...]:
    """Validate a zip member name into traversal-free segments, or raise.

    Backslashes are normalised to '/'. Absolute paths and any '.'/'..' segment
    are rejected (:class:`ZipSlipError`); every remaining segment must pass the
    spec-12 ``validate_name_segment`` rules (control chars / reserved names /
    separators). For an Overleaf template a reserved device name is renamed
    (``con.tex`` becomes ``con_.tex``) instead, since it is not a traversal.
    """
    normalised = raw.replace("\\", "/")
    if normalised.startswith("/"):
        raise ZipSlipError("Archive entry uses an absolute path.")
    segments = [s for s in normalised.split("/") if s != ""]
    if not segments:
        raise ZipSlipError("Archive entry has an empty path.")
    return tuple(_checked_segment(seg, template) for seg in segments)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix mode lives in the high 16 bits of external_attr (0 for archives made
    # on systems that do not record it — those are never symlinks).
    mode = info.external_attr >> 16
    return mode != 0 and stat.S_ISLNK(mode)


def _is_ignored(parts: tuple[str, ...]) -> bool:
    return parts[0] in _IGNORED_FIRST_SEGMENTS or parts[-1] in _IGNORED_BASENAMES


@dataclass(slots=True)
class _Planned:
    """Outcome of inspecting one central-directory entry."""

    entry: PlannedEntry | None = None
    skipped: int = 0


def _plan_entry(info: zipfile.ZipInfo, limits: ImportLimits) -> _Planned:
    """Inspect one central-directory entry without reading its bytes.

    Returns the importable leaf, or an empty result — with ``skipped`` set when the
    entry is a real file rejected for its extension, and clear when it is merely
    ignored. Raises a :class:`ZipImportError` subclass for an entry that makes the
    whole archive unsafe.
    """
    # Reject symlinks up front — never read or follow them, even for dirs.
    if _is_symlink(info):
        raise SymlinkEntryError("Archive contains a symlink entry.")

    parts = _safe_parts(info.filename, limits.template)
    # Folders are reconstructed from leaf parents; explicit dir entries only need
    # to pass the safety checks above.
    if _is_ignored(parts) or info.is_dir():
        return _Planned()

    classification = _classify(parts[-1], limits)
    if classification is None:
        return _Planned(skipped=1)
    if info.file_size > limits.max_file_bytes:
        raise ZipBombError("An archive entry exceeds the per-file size limit.")
    return _Planned(
        entry=PlannedEntry(
            zip_name=info.filename,
            parts=parts,
            is_dir=False,
            uncompressed_size=info.file_size,
            classification=classification,
        )
    )


def plan_entries(zf: zipfile.ZipFile, limits: ImportLimits) -> ImportPlan:
    """Validate the archive's central directory without extracting any bytes.

    Raises a :class:`ZipImportError` subclass on a malicious or oversized archive
    (zip-slip / symlink / bomb / too-many-entries / empty); otherwise returns the
    list of importable leaf entries plus the count skipped for a disallowed
    extension. All caps use the *declared* uncompressed sizes, so a bomb is
    rejected before any decompression happens.
    """
    entries: list[PlannedEntry] = []
    skipped = 0
    total_uncompressed = 0

    for info in zf.infolist():
        planned = _plan_entry(info, limits)
        skipped += planned.skipped
        if planned.entry is None:
            continue

        total_uncompressed += planned.entry.uncompressed_size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise ZipBombError("The archive's uncompressed size exceeds the limit.")
        entries.append(planned.entry)
        if len(entries) > limits.max_entries:
            raise ZipEntryCountError("The archive contains too many entries.")

    if not entries:
        raise EmptyArchiveError("The archive contains no importable files.")
    return ImportPlan(entries=entries, skipped=skipped, template=limits.template)
