"""Apply a push's text to the live documents as minimal CRDT edits (spec 121 §5.4 step 3).

The path is the one a history restore takes: ``DocumentManager`` applies the update to the room, the update
is persisted with origin ``git-push``, captured in history under the pusher's name, and broadcast to every
connected client. Collaborators' edits made since the writer's base survive; see ``textmerge``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from inkstave.modules.collab import encode_update
from inkstave.modules.git.push.apply import TextTarget
from inkstave.modules.git.push.textmerge import Conflict, plan_text_edits

if TYPE_CHECKING:
    from collections.abc import Callable

    from inkstave.modules.collab.ws.components import CollabComponents

GIT_PUSH_ORIGIN = "git-push"


def _planner(target: TextTarget) -> Callable[[str], tuple[list[tuple[int, int, str]], list[Conflict]]]:
    def plan(live: str) -> tuple[list[tuple[int, int, str]], list[Conflict]]:
        edits, conflicts = plan_text_edits(live, target.old, target.new)
        return [(edit.start, edit.end, edit.text) for edit in edits], conflicts

    return plan


def _warning(target: TextTarget, conflict: Conflict) -> str:
    label = "/".join(target.path)
    return (
        f"{label}: lines {conflict.first_line}–{conflict.last_line} were also edited in Inkstave; "
        "the pushed version was kept"
    )


async def apply_live_texts(
    collab: CollabComponents,
    *,
    project_id: UUID,
    author_id: UUID,
    targets: list[TextTarget],
) -> list[str]:
    """Apply each target's text to its live document. Returns the warnings for conflicting regions."""
    warnings: list[str] = []
    now = datetime.now(UTC)
    for target in targets:
        update, conflicts = await collab.manager.apply_server_edits(
            target.doc_id, _planner(target), GIT_PUSH_ORIGIN
        )
        warnings.extend(_warning(target, conflict) for conflict in conflicts)
        if update:
            if collab.history is not None:
                # Flush what editors typed first, so the push is recorded as its own version.
                await collab.history.flush_doc(doc_id=target.doc_id, reason="manual")
                await collab.history.capture_update(
                    project_id=project_id,
                    doc_id=target.doc_id,
                    update=update,
                    author_id=author_id,
                    at=now,
                    origin=GIT_PUSH_ORIGIN,
                )
                await collab.history.flush_doc(doc_id=target.doc_id, reason="manual")
            await collab.redis_bridge.publish(target.doc_id, GIT_PUSH_ORIGIN, encode_update(update))
        # Write the live text to documents.content now, so a fetch right after the push sees it. This
        # does not compact the update log, so the git-push origin stays on its rows (as for a restore).
        await collab.manager.flush_text_now(target.doc_id)
    return warnings
