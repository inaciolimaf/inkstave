"""The agent turn of a lived-in project: a user message, the reply, and its open proposal."""

from __future__ import annotations

from uuid import UUID

from inkstave.modules.agent.diffs.compute import compute_diff, content_hash
from inkstave.modules.agent.diffs.models import ProposedDiff
from inkstave.modules.agent.models import AgentMessage


def proposal_rows(
    project_id: UUID,
    session_id: UUID,
    doc_id: UUID,
    proposal_id: UUID,
    reply_id: UUID,
    current: str,
    proposed: str,
) -> list[object]:
    """A user turn, the agent's reply, and the open proposal that reply made for ``chapters/intro.tex``."""
    diff_text, hunks, stats = compute_diff(current, proposed, path="chapters/intro.tex")
    proposal = ProposedDiff(
        id=proposal_id,
        session_id=session_id,
        project_id=project_id,
        doc_id=doc_id,
        path="chapters/intro.tex",
        base_version="1",
        base_hash=content_hash(current),
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
