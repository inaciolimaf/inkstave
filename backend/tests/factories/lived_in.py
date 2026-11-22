"""A "lived-in" project: the data a real project already carries before a test touches it.

Empty fixtures hid bug 5548812: a document with content before its first edit reconstructed its
whole history as empty. This builder writes that kind of data with plain inserts (no service
calls, no compile, no LLM), so it stays well under 200 ms per build:

* a root folder; ``main.tex``, the root document, with ``\\input`` of two chapters, a bibliography
  and a figure; ``chapters/intro.tex``, ``chapters/methods.tex``, ``refs.bib``;
* ``figures/plot.png``, a binary blob written to the object store;
* ``appendix.tex``, an older document with content and **no** history rows (it predates history);
* ``main.tex`` with two recorded history versions, and ``intro.tex`` with a comment thread;
* an owner, an editor collaborator, a view share link and a pending agent proposal on ``intro.tex``.

Use it through the ``lived_in_project`` fixture in ``tests/integration``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.modules.agent.diffs.compute import compute_diff, content_hash
from inkstave.modules.agent.diffs.models import ProposedDiff
from inkstave.modules.agent.models import AgentMessage, AgentSession
from inkstave.modules.collab.crdt.ydocument import YDocument
from inkstave.modules.discussion.comments.models import CommentMessage, CommentThread
from inkstave.modules.history.models import HistoryChunk, HistoryUpdate
from inkstave.modules.projects.models.document import Document
from inkstave.modules.projects.models.file import File
from inkstave.modules.projects.models.membership import MembershipRole, MembershipStatus, ProjectMembership
from inkstave.modules.projects.models.project import Project
from inkstave.modules.projects.models.share_link import ProjectShareLink, ShareLinkRole
from inkstave.modules.projects.models.tree_entity import TreeEntity, TreeEntityType
from tests.factories.user import UserFactory

if TYPE_CHECKING:
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.auth import User

MAIN_V1 = "\\documentclass{article}\n"
MAIN_TEX = (
    "\\documentclass{article}\n"
    "\\input{chapters/intro}\n"
    "\\input{chapters/methods}\n"
    "\\bibliographystyle{plain}\n"
    "\\bibliography{refs}\n"
    "\\begin{document}\n"
    "\\maketitle\n"
    "\\includegraphics{figures/plot}\n"
    "\\end{document}\n"
)
INTRO_TEX = "\\section{Introduction}\nLévy flights in café-style prose, seeded before any edit.\n"
METHODS_TEX = "\\section{Methods}\nWe follow \\cite{knuth84} closely.\n"
REFS_BIB = "@book{knuth84,\n  title={The TeXbook},\n  author={Knuth, Donald},\n  year={1984}\n}\n"
APPENDIX_TEX = "\\appendix\n\\section{Legacy notes}\nWritten before history existed.\n"
PLOT_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256))  # binary, not valid UTF-8: byte identity matters
COMMENT_BODY = "Is 'seeded' the right word here?"
PROPOSED_INTRO = INTRO_TEX.replace("seeded before any edit", "kept from the first save")
SHARE_TOKEN = "lived-in-share-token"
FILE_PATH = "figures/plot.png"
FOLDERS = ("chapters", "figures")
# Every document path and its text. ``main.tex`` is the root document.
DOC_CONTENTS: dict[str, str] = {
    "main.tex": MAIN_TEX,
    "chapters/intro.tex": INTRO_TEX,
    "chapters/methods.tex": METHODS_TEX,
    "refs.bib": REFS_BIB,
    "appendix.tex": APPENDIX_TEX,
}
_NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


@dataclass
class LivedInProject:
    """Handles to the rows the builder wrote. ``ids`` maps every path to its tree-entity id."""

    project: Project
    owner: User
    collaborator: User
    ids: dict[str, UUID]
    folder_ids: dict[str, UUID]
    contents: dict[str, str] = field(default_factory=lambda: dict(DOC_CONTENTS))
    blob_key: str = ""
    thread_id: UUID = field(default_factory=uuid4)
    session_id: UUID = field(default_factory=uuid4)
    proposal_id: UUID = field(default_factory=uuid4)
    share_link_id: UUID = field(default_factory=uuid4)

    @property
    def project_id(self) -> UUID:
        return self.project.id

    @property
    def main_id(self) -> UUID:
        return self.ids["main.tex"]


def _folder_rows(project_id: UUID, root_id: UUID) -> tuple[list[TreeEntity], dict[str, UUID]]:
    """The root folder and the sub-folders, with their ids."""
    root = TreeEntity(
        id=root_id,
        project_id=project_id,
        parent_id=None,
        type=TreeEntityType.folder,
        name="",
        is_root=True,
    )
    folder_ids = {name: uuid4() for name in FOLDERS}
    folders = [
        TreeEntity(
            id=folder_ids[name],
            project_id=project_id,
            parent_id=root_id,
            type=TreeEntityType.folder,
            name=name,
        )
        for name in FOLDERS
    ]
    return [root, *folders], folder_ids


def _tree_rows(project_id: UUID, root_id: UUID) -> tuple[list[TreeEntity], dict[str, UUID], dict[str, UUID]]:
    """Root, folders, then every document and the blob, with ids chosen up front."""
    rows, folder_ids = _folder_rows(project_id, root_id)
    ids: dict[str, UUID] = {}
    for path in [*DOC_CONTENTS, FILE_PATH]:
        folder, _, leaf = path.rpartition("/")
        ids[path] = uuid4()
        rows.append(
            TreeEntity(
                id=ids[path],
                project_id=project_id,
                parent_id=folder_ids[folder] if folder else root_id,
                type=TreeEntityType.file if path == FILE_PATH else TreeEntityType.doc,
                name=leaf,
            )
        )
    return rows, ids, folder_ids


def _document_rows(project_id: UUID, ids: dict[str, UUID]) -> list[Document]:
    return [
        Document(
            entity_id=ids[path],
            project_id=project_id,
            content=text,
            version=2 if path == "main.tex" else 1,
            size_bytes=len(text.encode("utf-8")),
        )
        for path, text in DOC_CONTENTS.items()
    ]


def _history_rows(
    project_id: UUID, doc_id: UUID, author_id: UUID, chunk_id: UUID
) -> tuple[HistoryChunk, list[HistoryUpdate]]:
    """Two recorded versions of ``main.tex``, replayed from an empty base."""
    doc = YDocument()
    payloads: list[bytes] = []
    doc.observe(lambda update, _origin: payloads.append(update))
    doc.replace_text(MAIN_V1)
    doc.replace_text(MAIN_TEX)
    base = YDocument().get_state()
    chunk = HistoryChunk(
        id=chunk_id,
        project_id=project_id,
        doc_id=doc_id,
        start_version=1,
        end_version=len(payloads),
        base_version=0,
        base_snapshot=base,
        base_snapshot_size=len(base),
        sealed=False,
    )
    return chunk, _update_rows(project_id, doc_id, author_id, chunk_id, payloads)


def _update_rows(
    project_id: UUID, doc_id: UUID, author_id: UUID, chunk_id: UUID, payloads: list[bytes]
) -> list[HistoryUpdate]:
    return [
        HistoryUpdate(
            chunk_id=chunk_id,
            project_id=project_id,
            doc_id=doc_id,
            version=version,
            timestamp=_NOW,
            author_id=author_id,
            payload=payload,
            payload_size=len(payload),
            op_count=1,
        )
        for version, payload in enumerate(payloads, start=1)
    ]


def _proposal_rows(
    project_id: UUID, session_id: UUID, doc_id: UUID, proposal_id: UUID, reply_id: UUID
) -> list[object]:
    """A user turn, the agent's reply, and the open proposal that reply made for ``chapters/intro.tex``."""
    diff_text, hunks, stats = compute_diff(INTRO_TEX, PROPOSED_INTRO, path="chapters/intro.tex")
    proposal = ProposedDiff(
        id=proposal_id,
        session_id=session_id,
        project_id=project_id,
        doc_id=doc_id,
        path="chapters/intro.tex",
        base_version="1",
        base_hash=content_hash(INTRO_TEX),
        diff_text=diff_text,
        hunks=hunks,
        stats=stats,
        message_id=reply_id,
        rationale="Make the introduction less tentative.",
    )
    ask = AgentMessage(session_id=session_id, seq=1, role="user", content="Tighten the introduction.")
    reply = AgentMessage(
        id=reply_id, session_id=session_id, seq=2, role="assistant", content="Here is a tighter version."
    )
    return [ask, reply, proposal]


async def build_lived_in_project(
    session: AsyncSession, object_store: ObjectStore, *, name: str = "Thesis"
) -> LivedInProject:
    """Write a lived-in project with plain inserts and return its handles. Nothing is committed."""
    owner = await UserFactory.create(session)
    collaborator = await UserFactory.create(session)
    project = Project(owner_id=owner.id, name=name)
    session.add(project)
    await session.flush()
    root_id = uuid4()
    rows, ids, folder_ids = _tree_rows(project.id, root_id)
    project.root_doc_id = ids["main.tex"]
    session.add_all(rows)
    await session.flush()
    session.add_all(_document_rows(project.id, ids))
    await session.flush()
    chunk_id = uuid4()
    chunk, updates = _history_rows(project.id, ids["main.tex"], owner.id, chunk_id)
    session.add(chunk)
    await session.flush()
    session.add_all(updates)
    lived = LivedInProject(
        project=project, owner=owner, collaborator=collaborator, ids=ids, folder_ids=folder_ids
    )
    await _attach_blob(session, object_store, lived)
    _attach_collaboration(session, lived)
    await _attach_discussion_and_agent(session, lived)
    await session.flush()
    return lived


async def _attach_blob(session: AsyncSession, store: ObjectStore, lived: LivedInProject) -> None:
    key = f"projects/{lived.project_id}/files/{lived.ids[FILE_PATH]}"
    await store.put(key, PLOT_PNG, content_type="image/png")
    lived.blob_key = key
    session.add(
        File(
            entity_id=lived.ids[FILE_PATH],
            project_id=lived.project_id,
            storage_key=key,
            content_type="image/png",
            size_bytes=len(PLOT_PNG),
            checksum_sha256=hashlib.sha256(PLOT_PNG).hexdigest(),
            original_filename="plot.png",
        )
    )


def _attach_collaboration(session: AsyncSession, lived: LivedInProject) -> None:
    for user, role in ((lived.owner, MembershipRole.owner), (lived.collaborator, MembershipRole.editor)):
        session.add(
            ProjectMembership(
                project_id=lived.project_id,
                user_id=user.id,
                role=role,
                status=MembershipStatus.active,
            )
        )
    session.add(
        ProjectShareLink(
            id=lived.share_link_id,
            project_id=lived.project_id,
            role=ShareLinkRole.viewer,
            token_hash=hashlib.sha256(SHARE_TOKEN.encode()).hexdigest(),
            created_by=lived.owner.id,
        )
    )


async def _attach_discussion(session: AsyncSession, lived: LivedInProject) -> None:
    """A comment thread on ``chapters/intro.tex`` with one message from the collaborator."""
    session.add(
        CommentThread(
            id=lived.thread_id,
            project_id=lived.project_id,
            document_id=lived.ids["chapters/intro.tex"],
            anchor_start=b"\x01seeded-start",
            anchor_end=b"\x01seeded-end",
            quoted_text="seeded",
            created_by=lived.collaborator.id,
        )
    )
    await session.flush()
    session.add(
        CommentMessage(
            thread_id=lived.thread_id,
            author_id=lived.collaborator.id,
            body=COMMENT_BODY,
            mentions=[],
            created_at=_NOW,
        )
    )


async def _attach_discussion_and_agent(session: AsyncSession, lived: LivedInProject) -> None:
    await _attach_discussion(session, lived)
    session.add(
        AgentSession(
            id=lived.session_id,
            project_id=lived.project_id,
            user_id=lived.owner.id,
            title="Polish",
            model="fake/model",
        )
    )
    await session.flush()
    rows = _proposal_rows(
        lived.project_id, lived.session_id, lived.ids["chapters/intro.tex"], lived.proposal_id, uuid4()
    )
    session.add_all(rows[:-1])
    await session.flush()
    session.add(rows[-1])


__all__ = [
    "APPENDIX_TEX",
    "COMMENT_BODY",
    "DOC_CONTENTS",
    "FILE_PATH",
    "INTRO_TEX",
    "MAIN_TEX",
    "MAIN_V1",
    "METHODS_TEX",
    "PLOT_PNG",
    "PROPOSED_INTRO",
    "REFS_BIB",
    "SHARE_TOKEN",
    "LivedInProject",
    "build_lived_in_project",
]
