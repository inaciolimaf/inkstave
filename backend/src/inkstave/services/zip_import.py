"""Zip-archive → project tree reconstruction (spec 101).

The security-critical, pure-ish core of project import: validate an archive's
central directory *without decompressing* (zip-slip / symlink / zip-bomb
defences), then reconstruct the tree by reusing the existing tree / document /
file services. Isolated here so it can be unit-tested over tiny in-memory zips
and so the ARQ job (``services/import_jobs.py``) stays thin.

This is an independent implementation; it shares no code with Overleaf's
``ArchiveManager`` (read for understanding only — AGPLv3 vs MIT).
"""

from __future__ import annotations

import asyncio
import stat
import zipfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from inkstave.db.models.tree_entity import TreeEntityType
from inkstave.errors import AppError
from inkstave.security.uploads import content_matches_extension, extension_of
from inkstave.services import document_service, file_service, tree_service
from inkstave.services.file_service import sniff_content_type
from inkstave.services.safe_path import InvalidNameError, validate_name_segment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.storage.base import ObjectStore

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


@dataclass(frozen=True)
class ImportLimits:
    max_zip_bytes: int
    max_uncompressed_bytes: int
    max_file_bytes: int
    max_entries: int
    allowed_extensions: frozenset[str]  # lower-cased, incl. dot


def limits_from_settings(settings: Settings) -> ImportLimits:
    return ImportLimits(
        max_zip_bytes=settings.import_max_zip_bytes,
        max_uncompressed_bytes=settings.import_max_uncompressed_bytes,
        max_file_bytes=settings.import_max_file_bytes,
        max_entries=settings.import_max_entries,
        allowed_extensions=frozenset(e.lower() for e in settings.import_allowed_extensions),
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


@dataclass
class ImportOutcome:
    folders_created: int = 0
    docs_created: int = 0
    files_created: int = 0
    skipped: int = 0  # entries skipped at reconstruction (oversize / bad MIME / conflict)
    root_doc_entity_id: UUID | None = None
    root_doc_path: tuple[str, ...] | None = None


# --------------------------------------------------------------------------- #
# Error taxonomy (mapped to ``error_type`` on the import row / friendly i18n)
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Planning: validate the central directory WITHOUT extracting bytes
# --------------------------------------------------------------------------- #

# Ignorable junk: first path segment / basename matches are dropped silently
# (not imported, not counted as skipped).
_IGNORED_FIRST_SEGMENTS = {"__MACOSX", ".git"}
_IGNORED_BASENAMES = {".DS_Store"}


def _classify(name: str, limits: ImportLimits) -> Literal["text", "binary"] | None:
    base = name.lower()
    ext = extension_of(name)
    if ext in TEXT_EXTENSIONS or base in TEXT_EXTENSIONS:
        return "text"
    if ext in limits.allowed_extensions:
        return "binary"
    return None


def _safe_parts(raw: str) -> tuple[str, ...]:
    """Validate a zip member name into traversal-free segments, or raise.

    Backslashes are normalised to '/'. Absolute paths and any '.'/'..' segment
    are rejected (:class:`ZipSlipError`); every remaining segment must pass the
    spec-12 ``validate_name_segment`` rules (control chars / reserved names /
    separators).
    """
    normalised = raw.replace("\\", "/")
    if normalised.startswith("/"):
        raise ZipSlipError("Archive entry uses an absolute path.")
    segments = [s for s in normalised.split("/") if s != ""]
    if not segments:
        raise ZipSlipError("Archive entry has an empty path.")
    for seg in segments:
        if seg in (".", ".."):
            raise ZipSlipError("Archive entry contains a path-traversal segment.")
        try:
            validate_name_segment(seg)
        except InvalidNameError as exc:
            raise ZipSlipError(f"Archive entry has an unsafe path segment: {seg!r}") from exc
    return tuple(segments)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix mode lives in the high 16 bits of external_attr (0 for archives made
    # on systems that do not record it — those are never symlinks).
    mode = info.external_attr >> 16
    return mode != 0 and stat.S_ISLNK(mode)


def _is_ignored(parts: tuple[str, ...]) -> bool:
    return parts[0] in _IGNORED_FIRST_SEGMENTS or parts[-1] in _IGNORED_BASENAMES


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
        # Reject symlinks up front — never read or follow them, even for dirs.
        if _is_symlink(info):
            raise SymlinkEntryError("Archive contains a symlink entry.")

        parts = _safe_parts(info.filename)
        if _is_ignored(parts):
            continue
        if info.is_dir():
            # Folders are reconstructed from leaf parents; explicit dir entries
            # only need to pass the safety checks above.
            continue

        classification = _classify(parts[-1], limits)
        if classification is None:
            skipped += 1
            continue

        size = info.file_size
        if size > limits.max_file_bytes:
            raise ZipBombError("An archive entry exceeds the per-file size limit.")
        total_uncompressed += size
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise ZipBombError("The archive's uncompressed size exceeds the limit.")

        entries.append(
            PlannedEntry(
                zip_name=info.filename,
                parts=parts,
                is_dir=False,
                uncompressed_size=size,
                classification=classification,
            )
        )
        if len(entries) > limits.max_entries:
            raise ZipEntryCountError("The archive contains too many entries.")

    if not entries:
        raise EmptyArchiveError("The archive contains no importable files.")
    return ImportPlan(entries=entries, skipped=skipped)


# --------------------------------------------------------------------------- #
# Encoding / decoding
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Root-doc detection
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Reconstruction: create folders / docs / files, reusing the existing services
# --------------------------------------------------------------------------- #


def _read_member_bounded(zf: zipfile.ZipFile, name: str, max_bytes: int) -> bytes:
    """Read one entry's decompressed bytes, capped so a lying header can't bomb us."""
    with zf.open(name) as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ZipBombError("An archive entry decompressed beyond its declared size.")
    return data


@dataclass
class _FolderCache:
    """Maps a lower-cased path tuple → folder entity id (None == project root)."""

    ids: dict[tuple[str, ...], UUID | None] = field(default_factory=lambda: {(): None})


async def _ensure_folder(
    session: AsyncSession,
    project_id: UUID,
    parts: tuple[str, ...],
    cache: _FolderCache,
    outcome: ImportOutcome,
) -> UUID | None:
    """Return the folder entity id for ``parts``, creating intermediates as needed."""
    key = tuple(p.lower() for p in parts)
    if key in cache.ids:
        return cache.ids[key]
    parent_id = await _ensure_folder(session, project_id, parts[:-1], cache, outcome)
    try:
        entity = await tree_service.create_entity(
            session, project_id, TreeEntityType.folder, parts[-1], parent_id
        )
        outcome.folders_created += 1
        folder_id: UUID | None = entity.id
    except tree_service.NameConflictError:
        # A sibling with this name (case-insensitive) already exists — reuse it.
        folder_id = await _find_child_folder(session, project_id, parent_id, parts[-1])
    cache.ids[key] = folder_id
    return folder_id


async def _find_child_folder(
    session: AsyncSession, project_id: UUID, parent_id: UUID | None, name: str
) -> UUID | None:
    from sqlalchemy import func, select

    from inkstave.db.models.tree_entity import TreeEntity

    stmt = select(TreeEntity.id).where(
        TreeEntity.project_id == project_id,
        TreeEntity.type == TreeEntityType.folder,
        func.lower(TreeEntity.name) == name.lower(),
    )
    if parent_id is None:
        stmt = stmt.where(TreeEntity.is_root.is_(False), TreeEntity.parent_id.isnot(None))
    else:
        stmt = stmt.where(TreeEntity.parent_id == parent_id)
    return (await session.execute(stmt)).scalars().first()


async def reconstruct_tree(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    zf: zipfile.ZipFile,
    plan: ImportPlan,
    *,
    settings: Settings,
) -> ImportOutcome:
    """Create folders/docs/files for the planned entries, reusing the services."""
    outcome = ImportOutcome(skipped=plan.skipped)
    cache = _FolderCache()
    text_blobs: dict[tuple[str, ...], bytes] = {}
    doc_ids: dict[tuple[str, ...], UUID] = {}
    max_file = settings.import_max_file_bytes

    for entry in plan.entries:
        parent_id = await _ensure_folder(session, project_id, entry.parts[:-1], cache, outcome)
        name = entry.parts[-1]
        if entry.classification == "text":
            raw = await asyncio.to_thread(_read_member_bounded, zf, entry.zip_name, max_file)
            content = decode_text(raw)
            if len(content.encode("utf-8")) > settings.max_document_bytes:
                outcome.skipped += 1
                continue
            entity = await tree_service.create_entity(
                session, project_id, TreeEntityType.doc, name, parent_id
            )
            await document_service.set_content_from_collab(session, entity.id, content)
            outcome.docs_created += 1
            text_blobs[entry.parts] = raw
            doc_ids[entry.parts] = entity.id
        else:
            try:
                await _import_binary(
                    session, store, project_id, parent_id, name, zf, entry, settings
                )
                outcome.files_created += 1
            except _SkipEntry:
                outcome.skipped += 1

    root = detect_root_doc(plan.entries, text_blobs)
    if root is not None and root in doc_ids:
        outcome.root_doc_entity_id = doc_ids[root]
        outcome.root_doc_path = root
    return outcome


class _SkipEntry(Exception):
    """Internal: a binary entry could not be imported and is recorded as skipped."""


async def _import_binary(
    session: AsyncSession,
    store: ObjectStore,
    project_id: UUID,
    parent_id: UUID | None,
    name: str,
    zf: zipfile.ZipFile,
    entry: PlannedEntry,
    settings: Settings,
) -> None:
    cap = min(settings.import_max_file_bytes, settings.max_upload_bytes)
    data = await asyncio.to_thread(_read_member_bounded, zf, entry.zip_name, cap)
    # Validate the sniffed type BEFORE creating any entity, so a rejected binary
    # leaves no orphan tree node behind.
    content_type = sniff_content_type(data[: settings.storage_stream_chunk_bytes], None)
    if content_type not in settings.allowed_upload_mime or not content_matches_extension(
        name, content_type
    ):
        raise _SkipEntry()

    pos = {"i": 0}

    async def reader(size: int) -> bytes:
        chunk = data[pos["i"] : pos["i"] + size]
        pos["i"] += len(chunk)
        return chunk

    try:
        await file_service.upload_file(
            session, store, project_id, parent_id, name, reader, content_type, name
        )
    except (
        file_service.UnsupportedMediaTypeError,
        file_service.FileTooLargeError,
        tree_service.NameConflictError,
    ) as exc:
        raise _SkipEntry() from exc
