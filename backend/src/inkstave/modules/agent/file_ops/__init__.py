"""File operations the agent proposes: staged in a turn, stored here, decided by the user."""

from __future__ import annotations

from typing import TYPE_CHECKING

from inkstave.modules.agent.file_ops import repository as repo
from inkstave.modules.agent.file_ops.models import ProposedFileOp, ProposedFileOpStatus

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.agent.graph.state import AgentState
    from inkstave.modules.agent.models import AgentSession


async def materialize_file_ops(
    *, state: AgentState, db: AsyncSession, session: AgentSession, message_id: UUID | None
) -> list[ProposedFileOp]:
    """Store the turn's staged operations. Nothing in the project changes here."""
    rows: list[ProposedFileOp] = []
    for staged in state.get("staged_file_ops", []):
        await repo.mark_superseded(db, session_id=session.id, path=staged.path)
        rows.append(
            ProposedFileOp(
                session_id=session.id,
                message_id=message_id,
                project_id=session.project_id,
                entity_id=staged.entity_id,
                kind=staged.kind.value,
                entity_type=staged.entity_type,
                path=staged.path,
                new_path=staged.new_path,
                content=staged.content,
                affected_paths=staged.affected_paths,
                status=ProposedFileOpStatus.proposed.value,
                rationale=staged.rationale,
            )
        )
    db.add_all(rows)
    await db.flush()
    return rows


__all__ = ["ProposedFileOp", "ProposedFileOpStatus", "materialize_file_ops", "repo"]
