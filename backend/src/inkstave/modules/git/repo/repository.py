"""Bare repositories on disk, written with dulwich (spec 121). Synchronous: callers run these in threads.

One repository per project lives at ``{GIT_REPOS_ROOT}/{project_id}.git`` and has one branch, ``main``.
Every function opens the repository itself, so no dulwich object is shared between threads.
"""

from __future__ import annotations

import stat
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from dulwich.objects import Blob, Commit, ObjectID, ShaFile, Tree
from dulwich.refs import Ref
from dulwich.repo import Repo

if TYPE_CHECKING:
    from dulwich.object_store import BaseObjectStore

MAIN_REF = Ref(b"refs/heads/main")
AUTHOR = b"Inkstave <noreply@inkstave>"
SNAPSHOT_MESSAGE = b"Update from Inkstave\n"
REGULAR_FILE_MODE = stat.S_IFREG | 0o644
DIRECTORY_MODE = stat.S_IFDIR

# A tree entry: the path below the root as byte segments, its mode and the blob or tree it points to.
TreeItem = tuple[tuple[bytes, ...], int, ObjectID]


def repo_dir(root: str, project_id: UUID) -> Path:
    return Path(root) / f"{project_id}.git"


def open_or_create(path: Path) -> Repo:
    """Open the bare repository at ``path``, creating it with ``main`` as its HEAD when it is missing."""
    if (path / "HEAD").is_file():
        return Repo(str(path))
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init_bare(str(path))
    repo.refs.set_symbolic_ref(Ref(b"HEAD"), MAIN_REF)
    return repo


def main_head(repo: Repo) -> ObjectID | None:
    """The commit ``main`` points to, or ``None`` before the first snapshot."""
    try:
        return ObjectID(repo.refs[MAIN_REF])
    except KeyError:
        return None


def build_tree(store: BaseObjectStore, items: Iterable[TreeItem]) -> Tree:
    """Write the nested trees for ``items`` into ``store`` and return the root tree (not yet stored)."""
    tree = Tree()
    folders: dict[bytes, list[TreeItem]] = {}
    for parts, mode, sha in items:
        if len(parts) == 1:
            tree.add(parts[0], mode, sha)
        else:
            folders.setdefault(parts[0], []).append((parts[1:], mode, sha))
    for name, children in folders.items():
        subtree = build_tree(store, children)
        store.add_object(subtree)
        tree.add(name, DIRECTORY_MODE, subtree.id)
    return tree


def snapshot_commit(path: Path, files: Sequence[tuple[tuple[str, ...], bytes]]) -> str:
    """Commit the project's files on ``main`` unless ``main`` already holds exactly this tree.

    Returns the sha of ``main`` after the call. A repeated snapshot of an unchanged project adds nothing.
    """
    with open_or_create(path) as repo:
        store = repo.object_store
        items: list[TreeItem] = []
        for parts, data in files:
            blob = Blob.from_string(data)
            store.add_object(blob)
            items.append((tuple(part.encode("utf-8") for part in parts), REGULAR_FILE_MODE, blob.id))
        root = build_tree(store, items)
        store.add_object(root)
        head = main_head(repo)
        if head is not None and _commit(repo, head).tree == root.id:
            return head.decode("ascii")
        commit = new_commit(root.id, [head] if head is not None else [], SNAPSHOT_MESSAGE)
        store.add_object(commit)
        repo.refs.set_if_equals(MAIN_REF, head, commit.id)
        return commit.id.decode("ascii")


def _commit(repo: Repo, sha: ObjectID) -> Commit:
    obj: ShaFile = repo[sha]
    if not isinstance(obj, Commit):
        raise TypeError(f"{sha!r} is not a commit")
    return obj


def new_commit(tree_id: ObjectID, parents: list[ObjectID], message: bytes) -> Commit:
    commit = Commit()
    commit.tree = tree_id
    commit.parents = parents
    commit.author = commit.committer = AUTHOR
    commit.author_time = commit.commit_time = int(time.time())
    commit.author_timezone = commit.commit_timezone = 0
    commit.encoding = b"UTF-8"
    commit.message = message
    return commit


def is_ancestor_or_self(repo: Repo, ancestor: ObjectID, descendant: ObjectID) -> bool:
    """Whether ``ancestor`` is ``descendant`` or one of its ancestors (walks the parents)."""
    seen: set[ObjectID] = set()
    pending = [descendant]
    while pending:
        current = pending.pop()
        if current == ancestor:
            return True
        if current in seen:
            continue
        seen.add(current)
        obj = repo[current]
        if isinstance(obj, Commit):
            pending.extend(ObjectID(parent) for parent in obj.parents)
    return False
