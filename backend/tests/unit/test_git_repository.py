"""Spec 121 §8: the bare repository layer on dulwich, with no database. Snapshots, rename detection, ancestry."""

from __future__ import annotations

from pathlib import Path

from dulwich.objects import ObjectID

from inkstave.modules.git.push.changes import collect_changes
from inkstave.modules.git.repo.repository import (
    MAIN_REF,
    is_ancestor_or_self,
    main_head,
    open_or_create,
    snapshot_commit,
)

_BODY = "".join(f"line {n} of a long paragraph of writing\n" for n in range(40))


def _commit_files(path: Path, files: dict[tuple[str, ...], bytes]) -> str:
    return snapshot_commit(path, list(files.items()))


def test_a_repeated_snapshot_of_an_unchanged_project_adds_no_commit(tmp_path: Path) -> None:
    repo_path = tmp_path / "p.git"
    first = _commit_files(repo_path, {("main.tex",): b"hello\n"})
    second = _commit_files(repo_path, {("main.tex",): b"hello\n"})
    assert first == second
    with open_or_create(repo_path) as repo:
        assert main_head(repo) == ObjectID(first.encode())
        assert repo[ObjectID(first.encode())].parents == []  # the single initial commit


def test_a_changed_project_commits_on_top_of_main(tmp_path: Path) -> None:
    repo_path = tmp_path / "p.git"
    first = _commit_files(repo_path, {("main.tex",): b"hello\n"})
    second = _commit_files(repo_path, {("main.tex",): b"hello there\n", ("sub", "a.tex"): b"x\n"})
    assert second != first
    with open_or_create(repo_path) as repo:
        commit = repo[ObjectID(second.encode())]
        assert commit.parents == [ObjectID(first.encode())]
        assert commit.message == b"Update from Inkstave\n"
        assert commit.author == b"Inkstave <noreply@inkstave>"


def test_the_lost_directory_is_recreated_as_a_single_commit(tmp_path: Path) -> None:
    repo_path = tmp_path / "p.git"
    _commit_files(repo_path, {("main.tex",): b"hello\n"})
    for child in sorted(repo_path.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    repo_path.rmdir()
    head = _commit_files(repo_path, {("main.tex",): b"hello\n"})
    with open_or_create(repo_path) as repo:
        assert repo.refs[MAIN_REF] == head.encode()
        assert repo[ObjectID(head.encode())].parents == []


def test_renames_at_ninety_percent_similarity_are_detected(tmp_path: Path) -> None:
    repo_path = tmp_path / "p.git"
    first = _commit_files(repo_path, {("chapter.tex",): _BODY.encode(), ("keep.tex",): b"stable\n"})
    second = _commit_files(repo_path, {("intro.tex",): _BODY.encode(), ("keep.tex",): b"stable\n"})
    with open_or_create(repo_path) as repo:
        old_tree = repo[ObjectID(first.encode())].tree
        new_tree = repo[ObjectID(second.encode())].tree
        changes = collect_changes(repo.object_store, old_tree, new_tree)
    assert changes.renames == [(("chapter.tex",), ("intro.tex",))]
    assert changes.deletes == []
    assert changes.writes == []  # identical content: a move, not a rewrite
    assert sorted(changes.paths) == [("intro.tex",), ("keep.tex",)]


def test_adds_modifies_and_deletes_are_listed_with_old_bytes(tmp_path: Path) -> None:
    repo_path = tmp_path / "p.git"
    first = _commit_files(repo_path, {("a.tex",): b"one\n", ("gone.tex",): b"bye\n"})
    second = _commit_files(repo_path, {("a.tex",): b"two\n", ("new.tex",): b"fresh\n"})
    with open_or_create(repo_path) as repo:
        changes = collect_changes(
            repo.object_store,
            repo[ObjectID(first.encode())].tree,
            repo[ObjectID(second.encode())].tree,
        )
    by_path = {write.parts: write for write in changes.writes}
    assert by_path[("a.tex",)].old == b"one\n" and by_path[("a.tex",)].data == b"two\n"
    assert by_path[("new.tex",)].old is None
    assert changes.deletes == [("gone.tex",)]


def test_ancestry_walks_the_parents(tmp_path: Path) -> None:
    repo_path = tmp_path / "p.git"
    first = _commit_files(repo_path, {("a.tex",): b"1\n"})
    second = _commit_files(repo_path, {("a.tex",): b"2\n"})
    third = _commit_files(repo_path, {("a.tex",): b"3\n"})
    with open_or_create(repo_path) as repo:
        assert is_ancestor_or_self(repo, ObjectID(first.encode()), ObjectID(third.encode()))
        assert is_ancestor_or_self(repo, ObjectID(third.encode()), ObjectID(third.encode()))
        assert not is_ancestor_or_self(repo, ObjectID(third.encode()), ObjectID(first.encode()))
        assert second != third
