"""What a push changes, and the rules it must pass before anything is written (spec 121).

``collect_changes`` reads the difference between two trees with dulwich, including renames. It is
synchronous and runs in a thread. ``validate_changes`` is pure: it returns one message per problem, and
a push with any message is refused whole. The rules are the ones the web project applies to uploads,
zip imports and tree operations: name segments, the archive path rules, extension and sniffed type,
size caps and the node cap.
"""

from __future__ import annotations

import mimetypes
import stat
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from dulwich.diff_tree import RenameDetector, TreeChange, tree_changes
from dulwich.object_store import iter_tree_contents
from dulwich.objects import Blob, TreeEntry

from inkstave.modules.projects.content.files import sniff_content_type
from inkstave.modules.projects.content.uploads import (
    content_matches_extension,
    extension_allowed,
    extension_of,
)
from inkstave.modules.projects.transfer.zip_import.plan import TEXT_EXTENSIONS
from inkstave.modules.projects.tree.safe_path import InvalidNameError, validate_name_segment

if TYPE_CHECKING:
    from dulwich.object_store import BaseObjectStore
    from dulwich.objects import ObjectID

    from inkstave.core.config.settings import Settings

Path = tuple[str, ...]
Kind = Literal["text", "file"]

RENAME_SIMILARITY_PERCENT = 90
_IGNORED_SEGMENTS = frozenset({".DS_Store", "__MACOSX"})
_SNIFF_BYTES = 65_536
_MAX_PROBLEMS = 50
_SYMLINK_OR_GITLINK = (stat.S_IFLNK, 0o160000)


@dataclass(frozen=True, slots=True)
class FileWrite:
    """A path whose content is new: an added file, or a modified one with the bytes it had before."""

    parts: Path
    data: bytes
    old: bytes | None
    mode: int


@dataclass(slots=True)
class PushChanges:
    writes: list[FileWrite] = field(default_factory=list)
    deletes: list[Path] = field(default_factory=list)
    renames: list[tuple[Path, Path]] = field(default_factory=list)
    # Every file path of the resulting tree, and the number of folders it implies.
    paths: list[Path] = field(default_factory=list)
    folder_count: int = 0


def kind_of(name: str, settings: Settings) -> Kind | None:
    """``text`` for a document, ``file`` for an uploaded binary, ``None`` for a type nobody may push."""
    if extension_of(name) in TEXT_EXTENSIONS or name.lower() in TEXT_EXTENSIONS:
        return "text"
    if extension_allowed(name, settings.upload_allowed_extensions):
        return "file"
    return None


def _decode_part(raw: bytes) -> str:
    # Invalid UTF-8 survives as surrogate escapes, so validation can name the path instead of crashing.
    return raw.decode("utf-8", errors="surrogateescape")


def _folder_prefixes(paths: list[Path]) -> int:
    folders: set[Path] = set()
    for parts in paths:
        for depth in range(1, len(parts)):
            folders.add(parts[:depth])
    return len(folders)


def _parts_of(entry: TreeEntry) -> Path:
    return tuple(_decode_part(part) for part in entry.path.split(b"/"))


def _tree_paths(store: BaseObjectStore, tree_id: ObjectID) -> list[Path]:
    return [_parts_of(entry) for entry in iter_tree_contents(store, tree_id)]


def _blob_data(store: BaseObjectStore, sha: ObjectID) -> bytes:
    blob = store[sha]
    if not isinstance(blob, Blob):
        raise TypeError(f"{sha!r} is not a blob")
    return blob.data


def collect_changes(store: BaseObjectStore, old_tree: ObjectID | None, new_tree: ObjectID) -> PushChanges:
    """Read ``old_tree -> new_tree``: adds, modifications, deletions and renames at 90 % similarity."""
    changes = PushChanges()
    detector = RenameDetector(store, rename_threshold=RENAME_SIMILARITY_PERCENT)
    for change in tree_changes(store, old_tree, new_tree, rename_detector=detector):
        _record(store, changes, change)
    changes.paths = _tree_paths(store, new_tree)
    changes.folder_count = _folder_prefixes(changes.paths)
    return changes


def _record(store: BaseObjectStore, changes: PushChanges, change: TreeChange) -> None:
    old, new = change.old, change.new
    if change.type == "delete" and old is not None:
        changes.deletes.append(_parts_of(old))
    elif change.type == "rename" and old is not None and new is not None:
        changes.renames.append((_parts_of(old), _parts_of(new)))
        if old.sha != new.sha:
            changes.writes.append(_write_for(store, new, old))
    elif change.type in ("add", "modify") and new is not None:
        changes.writes.append(_write_for(store, new, old if change.type == "modify" else None))


def _write_for(store: BaseObjectStore, new: TreeEntry, old: TreeEntry | None) -> FileWrite:
    return FileWrite(
        parts=_parts_of(new),
        data=_blob_data(store, new.sha),
        old=_blob_data(store, old.sha) if old is not None else None,
        mode=new.mode,
    )


def _segment_problem(segment: str) -> str | None:
    if segment in ("", ".", ".."):
        return "contains a path-traversal segment"
    if "\\" in segment or "/" in segment:
        return "contains a path separator"
    if any("\udc80" <= ch <= "\udcff" for ch in segment):
        return "is not valid UTF-8"
    if segment in _IGNORED_SEGMENTS:
        return "system files are not stored in projects"
    return _name_problem(segment)


def _name_problem(segment: str) -> str | None:
    """The projects' name rules, plus the rule that a name carries no surrounding spaces."""
    try:
        clean = validate_name_segment(segment)
    except InvalidNameError as exc:
        return str(exc)
    return None if clean == segment else "name has surrounding spaces"


def path_problems(parts: Path) -> list[str]:
    label = "/".join(parts)
    for segment in parts:
        problem = _segment_problem(segment)
        if problem is not None:
            return [f"{label}: {problem}"]
    return []


def _write_problems(write: FileWrite, settings: Settings) -> list[str]:
    label = "/".join(write.parts)
    name = write.parts[-1]
    if stat.S_IFMT(write.mode) in _SYMLINK_OR_GITLINK:
        return [f"{label}: symlinks and submodules are not supported"]
    kind = kind_of(name, settings)
    if kind is None:
        return [f"{label}: this file type is not allowed"]
    if kind == "text":
        return _text_problems(label, write.data, settings)
    return _binary_problems(label, name, write.data, settings)


def _text_problems(label: str, data: bytes, settings: Settings) -> list[str]:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{label}: text is not valid UTF-8"]
    if len(data) > settings.max_document_bytes:
        return [f"{label}: text is larger than {settings.max_document_bytes} bytes"]
    return []


def _binary_problems(label: str, name: str, data: bytes, settings: Settings) -> list[str]:
    if len(data) > settings.max_upload_bytes:
        return [f"{label}: file is larger than the upload limit of {settings.max_upload_bytes} bytes"]
    declared = mimetypes.guess_type(name)[0]
    content_type = sniff_content_type(data[:_SNIFF_BYTES], declared)
    if content_type not in settings.allowed_upload_mime or not content_matches_extension(name, content_type):
        return [f"{label}: file content does not match its extension or an allowed type"]
    return []


def _clash_problems(paths: list[Path]) -> list[str]:
    """Names are unique case-insensitively within a folder, so two paths that differ only in case clash."""
    seen: dict[tuple[str, ...], Path] = {}
    problems: list[str] = []
    for parts in paths:
        for depth in range(1, len(parts) + 1):
            prefix = parts[:depth]
            key = tuple(part.lower() for part in prefix)
            other = seen.setdefault(key, prefix)
            if other != prefix:
                problems.append(f"{'/'.join(prefix)}: clashes with {'/'.join(other)} (names ignore case)")
    return problems


def validate_changes(changes: PushChanges, settings: Settings) -> list[str]:
    """Every problem with the push, one message each; an empty list means it may be applied."""
    problems: list[str] = []
    for parts in [*changes.deletes, *(part for pair in changes.renames for part in pair)]:
        problems.extend(path_problems(parts))
    for write in changes.writes:
        path_issues = path_problems(write.parts)
        problems.extend(path_issues or _write_problems(write, settings))
    problems.extend(_clash_problems(changes.paths))
    nodes = len(changes.paths) + changes.folder_count
    if nodes > settings.tree_max_nodes:
        problems.append(f"the project would hold {nodes} entries, the limit is {settings.tree_max_nodes}")
    return problems[:_MAX_PROBLEMS]
