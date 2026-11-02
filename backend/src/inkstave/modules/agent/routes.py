"""Agent HTTP routes (spec 44): sessions, messages, event stream, cancel, diffs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from inkstave.core.config.agent import get_agent_settings
from inkstave.core.db.ownership import get_owned
from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.deps import get_redis, get_settings_dep
from inkstave.core.errors import AppError, ConflictError, ErrorEnvelope
from inkstave.modules.agent.deps import get_agent_enqueuer
from inkstave.modules.agent.diffs import repository as diff_repo
from inkstave.modules.agent.diffs.models import ProposedDiffStatus
from inkstave.modules.agent.graph import repository as agent_repo
from inkstave.modules.agent.models import AgentRunState, AgentSession
from inkstave.modules.agent.runs.events import request_cancel
from inkstave.modules.agent.runs.stream import sse_stream
from inkstave.modules.agent.schemas import (
    AgentMessageOut,
    AgentSessionOut,
    CreateSessionIn,
    PostMessageIn,
    PostMessageOut,
    ProposedDiffSummary,
    SessionDetailOut,
)
from inkstave.modules.auth import (
    get_current_user,
    rate_limit_named,
    sse_user,
)
from inkstave.modules.collab import flush_open_project_docs
from inkstave.modules.projects import ProjectNotFoundError, role_for

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.modules.agent.diffs.models import ProposedDiff
    from inkstave.modules.agent.runs.enqueuer import AgentEnqueuer
    from inkstave.modules.auth import User

router = APIRouter(prefix="/projects/{project_id}/agent", tags=["agent"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
}


class NotProjectMemberError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "not_project_member"

    def __init__(self) -> None:
        super().__init__("You are not a member of this project.")


class RunActiveError(ConflictError):
    error_type = "run_active"

    def __init__(self) -> None:
        super().__init__("A run is already active for this session.")


# States in which a run is genuinely in flight, so a new message must wait. The
# terminal states (``done``/``error``) and the initial ``idle`` all permit a
# fresh turn — otherwise a session would refuse every message after its first.
_ACTIVE_RUN_STATES = frozenset(
    {
        AgentRunState.queued.value,
        AgentRunState.running.value,
        AgentRunState.cancelling.value,
    }
)


class MessageTooLongError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "message_too_long"

    def __init__(self, max_chars: int) -> None:
        super().__init__("Message exceeds the maximum length.", details=[{"max_chars": max_chars}])


async def _require_member(session: AsyncSession, project_id: UUID, user_id: UUID) -> None:
    """404 for an unknown/deleted project, 403 for a non-member (spec 44)."""
    if not await agent_repo.project_is_live(session, project_id):
        raise ProjectNotFoundError()
    if await role_for(session, user_id, project_id) is None:
        raise NotProjectMemberError()


async def _owned_session(
    session: AsyncSession, project_id: UUID, session_id: UUID, user_id: UUID
) -> AgentSession:
    return await get_owned(
        session, AgentSession, session_id, user_id, not_found=ProjectNotFoundError(), project_id=project_id
    )


def _diff_summary(diff: ProposedDiff, *, include_hunks: bool) -> ProposedDiffSummary:
    out = ProposedDiffSummary.model_validate(diff)
    if not include_hunks:
        out.hunks = None
    return out


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentSessionOut,
    responses=_ERRORS,
)
async def create_session(
    project_id: UUID,
    body: CreateSessionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> AgentSessionOut:
    await _require_member(session, project_id, user.id)
    row = await agent_repo.create_session(
        session,
        project_id=project_id,
        user_id=user.id,
        model=get_agent_settings().agent_model,
        title=body.title,
    )
    return AgentSessionOut.model_validate(row)


@router.get("/sessions", response_model=list[AgentSessionOut], responses=_ERRORS)
async def list_sessions(
    project_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> list[AgentSessionOut]:
    await _require_member(session, project_id, user.id)
    rows = await agent_repo.list_sessions(session, project_id=project_id, user_id=user.id)
    return [AgentSessionOut.model_validate(r) for r in rows[:limit]]


@router.get("/sessions/{session_id}", response_model=SessionDetailOut, responses=_ERRORS)
async def get_session_detail(
    project_id: UUID,
    session_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> SessionDetailOut:
    await _require_member(session, project_id, user.id)
    row = await _owned_session(session, project_id, session_id, user.id)
    messages = await agent_repo.list_messages(session, session_id)
    diffs = await diff_repo.list_for_session(session, session_id)
    return SessionDetailOut(
        session=AgentSessionOut.model_validate(row),
        messages=[AgentMessageOut.model_validate(m) for m in messages],
        diffs=[
            _diff_summary(d, include_hunks=False)
            for d in diffs
            if d.status == ProposedDiffStatus.proposed.value
        ],
    )


@router.post(
    "/sessions/{session_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PostMessageOut,
    responses=_ERRORS,
    dependencies=[Depends(rate_limit_named("agent"))],
)
async def post_message(
    project_id: UUID,
    session_id: UUID,
    body: PostMessageIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    enqueuer: AgentEnqueuer = Depends(get_agent_enqueuer),
) -> PostMessageOut:
    await _require_member(session, project_id, user.id)
    row = await _owned_session(session, project_id, session_id, user.id)
    max_chars = get_agent_settings().agent_max_message_chars
    if len(body.content) > max_chars:
        raise MessageTooLongError(max_chars)
    if row.run_state in _ACTIVE_RUN_STATES:
        raise RunActiveError()  # 409 — one active run per session

    run_id = uuid4()
    row.run_state = AgentRunState.queued.value
    row.active_run_id = run_id
    await session.flush()
    # Materialise any open CRDT rooms so the worker's tools read current text, not
    # the debounced-stale documents.content column (spec 28/42).
    await flush_open_project_docs(getattr(request.app.state, "collab", None), session, project_id)
    await enqueuer.enqueue(session_id=row.id, run_id=run_id, user_message=body.content)
    stream_url = f"/api/v1/projects/{project_id}/agent/sessions/{session_id}/runs/{run_id}/events"
    return PostMessageOut(run_id=run_id, stream_url=stream_url)


@router.post(
    "/sessions/{session_id}/runs/{run_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
)
async def cancel_run(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    await _require_member(session, project_id, user.id)
    row = await _owned_session(session, project_id, session_id, user.id)
    await request_cancel(redis, run_id, get_agent_settings().agent_run_ttl_s)
    if row.active_run_id == run_id and row.run_state in (
        AgentRunState.queued.value,
        AgentRunState.running.value,
    ):
        row.run_state = AgentRunState.cancelling.value
        await session.flush()
    return {"status": "cancelling"}


@router.get("/sessions/{session_id}/runs/{run_id}/events", responses=_ERRORS)
async def run_events(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    user: User = Depends(sse_user),
    session: AsyncSession = UNIT_OF_WORK,
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    await _require_member(session, project_id, user.id)
    await _owned_session(session, project_id, session_id, user.id)
    return StreamingResponse(
        sse_stream(redis, run_id, get_agent_settings().agent_stream_heartbeat_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}/diffs", response_model=list[ProposedDiffSummary], responses=_ERRORS)
async def list_diffs(
    project_id: UUID,
    session_id: UUID,
    status_filter: Literal["proposed", "applied", "partially_applied", "rejected", "stale", "superseded"]
    | None = Query(None, alias="status"),
    include: str | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> list[ProposedDiffSummary]:
    await _require_member(session, project_id, user.id)
    await _owned_session(session, project_id, session_id, user.id)
    rows = await diff_repo.list_for_session(session, session_id)
    if status_filter is not None:
        rows = [r for r in rows if r.status == status_filter]
    include_hunks = include == "hunks"
    return [_diff_summary(r, include_hunks=include_hunks) for r in rows]
