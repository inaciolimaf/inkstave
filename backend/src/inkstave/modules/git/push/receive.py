"""The synchronous half of a push: read the commands, ingest the pack, and decide (spec 121 §5.4 step 1).

Everything here runs in a thread and writes nothing that changes ``main`` or the project. It returns either
a refusal, with the reason for each problem, or the changes the push makes and the commit it lands on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from dulwich.errors import ObjectFormatException
from dulwich.objects import Commit, ObjectID

from inkstave.modules.git.push.changes import PushChanges, collect_changes, validate_changes
from inkstave.modules.git.repo.protocol import ZERO_SHA, PushCommand, ingest_pack, parse_commands
from inkstave.modules.git.repo.repository import MAIN_REF, is_ancestor_or_self, main_head, open_or_create

if TYPE_CHECKING:
    from inkstave.core.config.settings import Settings

PULL_FIRST = "Pull first: the project changed in Inkstave."
ONLY_MAIN = "Only refs/heads/main can be pushed."
NO_DELETE = "Deleting main is not allowed."
MISSING_COMMIT = "The pushed commit is missing or is not a commit."


@dataclass(slots=True)
class PreparedPush:
    capabilities: set[bytes]
    refs: list[bytes] = field(default_factory=list)  # the refs the client asked to update
    new: ObjectID | None = None  # the commit main should point to
    head: ObjectID | None = None  # main as it is now
    changes: PushChanges = field(default_factory=PushChanges)
    unpack_error: str | None = None
    refusal: str | None = None  # the reason main is not updated
    messages: list[str] = field(default_factory=list)  # lines for the client's terminal

    @property
    def accepted(self) -> bool:
        return self.refusal is None and self.unpack_error is None


def _refusal_for(commands: list[PushCommand]) -> str | None:
    if any(command.ref != MAIN_REF for command in commands):
        return ONLY_MAIN
    if any(command.new == ZERO_SHA for command in commands):
        return NO_DELETE
    return None


def _new_commit(repo: object, sha: ObjectID) -> Commit | None:
    try:
        obj = repo[sha]  # type: ignore[index]
    except (KeyError, ObjectFormatException):
        return None
    return obj if isinstance(obj, Commit) else None


def _descends(repo: object, head: ObjectID | None, new: ObjectID) -> bool:
    return head is None or is_ancestor_or_self(repo, head, new)  # type: ignore[arg-type]


def prepare_push(repo_path: Path, body: bytes, settings: Settings) -> PreparedPush:
    """Read and judge one receive-pack request against the repository at ``repo_path``."""
    commands, capabilities, proto = parse_commands(body)
    prepared = PreparedPush(capabilities=capabilities, refs=[command.ref for command in commands])
    if not commands:
        return prepared
    with open_or_create(repo_path) as repo:
        if any(command.new != ZERO_SHA for command in commands):
            try:
                ingest_pack(repo, proto, settings.git_max_push_bytes)
            except Exception as exc:  # the pack is malformed, too large or truncated
                prepared.unpack_error = str(exc).replace("\n", " ") or "unpack failed"
                return prepared
        prepared.refusal = _refusal_for(commands)
        if prepared.refusal is None:
            _judge(repo, commands[0], prepared, settings)
    return prepared


def _judge(repo: object, command: PushCommand, prepared: PreparedPush, settings: Settings) -> None:
    head = main_head(repo)  # type: ignore[arg-type]
    prepared.head = head
    commit = _new_commit(repo, command.new)
    if commit is None:
        prepared.refusal = MISSING_COMMIT
        return
    if not _descends(repo, head, command.new):
        prepared.refusal = PULL_FIRST
        return
    prepared.new = command.new
    if head is not None and head == command.new:
        return  # the same state main already holds
    old_tree = repo[head].tree if head is not None else None  # type: ignore[index]
    prepared.changes = collect_changes(repo.object_store, old_tree, commit.tree)  # type: ignore[attr-defined]
    problems = validate_changes(prepared.changes, settings)
    if problems:
        prepared.refusal = "; ".join(problems)
        prepared.messages = problems
