"""Zip-archive → project tree reconstruction (spec 101).

The security-critical, pure-ish core of project import: validate an archive's
central directory *without decompressing* (zip-slip / symlink / zip-bomb
defences), then reconstruct the tree by reusing the existing tree / document /
file services. Isolated here so it can be unit-tested over tiny in-memory zips
and so the ARQ job (``services/import_jobs.py``) stays thin.

This is an independent implementation; it shares no code with Overleaf's
``ArchiveManager`` (read for understanding only — AGPLv3 vs MIT).
"""

from inkstave.modules.projects.transfer.zip_import.content import decode_text, detect_root_doc
from inkstave.modules.projects.transfer.zip_import.plan import (
    EmptyArchiveError,
    ImportLimits,
    ImportOutcome,
    ImportPlan,
    InvalidZipError,
    PlannedEntry,
    SymlinkEntryError,
    ZipBombError,
    ZipEntryCountError,
    ZipImportError,
    ZipSlipError,
    limits_from_settings,
    plan_entries,
)
from inkstave.modules.projects.transfer.zip_import.reconstruct import reconstruct_tree

__all__ = [
    "EmptyArchiveError",
    "ImportLimits",
    "ImportOutcome",
    "ImportPlan",
    "InvalidZipError",
    "PlannedEntry",
    "SymlinkEntryError",
    "ZipBombError",
    "ZipEntryCountError",
    "ZipImportError",
    "ZipSlipError",
    "decode_text",
    "detect_root_doc",
    "limits_from_settings",
    "plan_entries",
    "reconstruct_tree",
]
