"""Recording the user's decision on a proposed diff, hunk by hunk (spec 110).

The browser reviews the hunks inside the text and reports, once, which were accepted, rejected or
found stale. The backend checks the report against the stored hunks and sets the proposal's status.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from inkstave.core.errors import AppError, ConflictError, NotFoundError
from inkstave.modules.agent.diffs.models import ProposedDiffStatus

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.modules.agent.diffs.models import ProposedDiff
    from inkstave.modules.agent.diffs.schemas import DiffOutcomeIn


class DiffNotFoundError(NotFoundError):
    error_type = "diff_not_found"

    def __init__(self) -> None:
        super().__init__("This proposal does not exist.")


class DiffForbiddenError(AppError):
    status_code = 403
    error_type = "diff_forbidden"

    def __init__(self) -> None:
        super().__init__("Recording a decision requires editor access.")


class InvalidOutcomeError(AppError):
    status_code = 422
    error_type = "invalid_outcome"

    def __init__(self) -> None:
        super().__init__("Every hunk must appear exactly once across accepted, rejected and stale.")


class AlreadyDecidedError(ConflictError):
    error_type = "already_decided"

    def __init__(self, stored_status: str) -> None:
        super().__init__("This proposal was already decided.", details=[{"status": stored_status}])


def outcome_status(total: int, accepted: int, stale: int) -> str:
    """The proposal's status from its hunk counts: all accepted, none accepted, or a mix."""
    if total and accepted == total:
        return ProposedDiffStatus.applied.value
    if accepted == 0:
        return ProposedDiffStatus.stale.value if stale else ProposedDiffStatus.rejected.value
    return ProposedDiffStatus.partially_applied.value


def check_outcome(hunk_ids: list[str], body: DiffOutcomeIn) -> None:
    """Each hunk id of the diff must appear exactly once across the three lists."""
    listed = [*body.accepted, *body.rejected, *body.stale]
    if len(listed) != len(set(listed)) or set(listed) != set(hunk_ids):
        raise InvalidOutcomeError()


async def record_outcome(db: AsyncSession, diff: ProposedDiff, body: DiffOutcomeIn, user_id: UUID) -> None:
    """Store the decision once. The caller holds the row lock (``with_for_update``)."""
    if diff.status != ProposedDiffStatus.proposed.value:
        raise AlreadyDecidedError(diff.status)
    check_outcome([str(h["hunk_id"]) for h in diff.hunks], body)
    diff.status = outcome_status(len(diff.hunks), len(body.accepted), len(body.stale))
    diff.decided_hunks = {"accepted": body.accepted, "rejected": body.rejected, "stale": body.stale}
    diff.decided_at = datetime.now(UTC)
    diff.decided_by = user_id
    await db.flush()
