"""Agent HTTP routes (spec 44): sessions, messages, event stream, cancel, diffs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from inkstave.agent import repository as agent_repo
from inkstave.agent.api.events import request_cancel
from inkstave.agent.api.schemas import (
    AgentMessageOut,
    AgentSessionOut,
    CreateSessionIn,
    PostMessageIn,
    PostMessageOut,
    ProposedDiffSummary,
    SessionDetailOut,
)
from inkstave.agent.api.stream import sse_stream
from inkstave.agent.diffs import repository as diff_repo
from inkstave.agent.diffs.models import ProposedDiffStatus
from inkstave.agent.models import AgentRunState, AgentSession
from inkstave.agent.settings import get_agent_settings
from inkstave.auth.dependencies import (
    NotAuthenticatedError,
    _resolve_user,
    bearer_scheme,
    get_current_user,
)
from inkstave.authorization.service import role_for
from inkstave.collab.flush import flush_open_project_docs
from inkstave.db.models.project import Project
from inkstave.db.session import get_db_session
from inkstave.dependencies import get_agent_enqueuer, get_redis, get_settings_dep, get_token_service
from inkstave.errors import AppError, ConflictError, ErrorEnvelope
from inkstave.security.rate_limit import rate_limit_named
from inkstave.services.project import ProjectNotFoundError

if TYPE_CHECKING:
    from fastapi.security import HTTPAuthorizationCredentials
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.agent.api.enqueuer import AgentEnqueuer
    from inkstave.agent.diffs.models import ProposedDiff
    from inkstave.auth.tokens import TokenService
    from inkstave.config import Settings
    from inkstave.db.models.user import User

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

    def __init__(self) -> None:
        super().__init__("Message exceeds the maximum length.")


async def _require_member(session: AsyncSession, project_id: UUID, user_id: UUID) -> None:
    """404 for an unknown/deleted project, 403 for a non-member (spec 44)."""
    project = await session.scalar(
        select(Project.id).where(Project.id == project_id, Project.deleted_at.is_(None))
    )
    if project is None:
        raise ProjectNotFoundError()
    if await role_for(session, user_id, project_id) is None:
        raise NotProjectMemberError()


async def _owned_session(
    session: AsyncSession, project_id: UUID, session_id: UUID, user_id: UUID
) -> AgentSession:
    row = await agent_repo.get_session(session, session_id)
    if row is None or row.project_id != project_id or row.user_id != user_id:
        raise ProjectNotFoundError()  # 404 — do not leak another user's session
    return row


def _diff_summary(diff: ProposedDiff, *, include_hunks: bool) -> ProposedDiffSummary:
    out = ProposedDiffSummary.model_validate(diff)
    if include_hunks:
        out.hunks = diff.hunks
    return out


# --- sessions -------------------------------------------------------------- #


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
    session: AsyncSession = Depends(get_db_session),
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
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentSessionOut]:
    await _require_member(session, project_id, user.id)
    rows = await agent_repo.list_sessions(session, project_id=project_id, user_id=user.id)
    return [AgentSessionOut.model_validate(r) for r in rows[:limit]]


@router.get("/sessions/{session_id}", response_model=SessionDetailOut, responses=_ERRORS)
async def get_session_detail(
    project_id: UUID,
    session_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
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


# --- messages + run -------------------------------------------------------- #


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
    session: AsyncSession = Depends(get_db_session),
    enqueuer: AgentEnqueuer = Depends(get_agent_enqueuer),
) -> PostMessageOut:
    await _require_member(session, project_id, user.id)
    row = await _owned_session(session, project_id, session_id, user.id)
    if len(body.content) > get_agent_settings().agent_max_message_chars:
        raise MessageTooLongError()
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
    session: AsyncSession = Depends(get_db_session),
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


# --- SSE event stream (query-param token auth) ----------------------------- #


async def _sse_user(
    access_token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_service: TokenService = Depends(get_token_service),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    token = (credentials.credentials if credentials else None) or access_token
    if not token:
        raise NotAuthenticatedError()
    return await _resolve_user(token, token_service, session)


@router.get("/sessions/{session_id}/runs/{run_id}/events", responses=_ERRORS)
async def run_events(
    project_id: UUID,
    session_id: UUID,
    run_id: UUID,
    user: User = Depends(_sse_user),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    await _require_member(session, project_id, user.id)
    await _owned_session(session, project_id, session_id, user.id)
    return StreamingResponse(
        sse_stream(redis, run_id, get_agent_settings().agent_stream_heartbeat_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- diffs ----------------------------------------------------------------- #


@router.get(
    "/sessions/{session_id}/diffs", response_model=list[ProposedDiffSummary], responses=_ERRORS
)
async def list_diffs(
    project_id: UUID,
    session_id: UUID,
    status_filter: Literal[
        "proposed", "applied", "partially_applied", "rejected", "stale", "superseded"
    ]
    | None = Query(None, alias="status"),
    include: str | None = Query(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProposedDiffSummary]:
    await _require_member(session, project_id, user.id)
    await _owned_session(session, project_id, session_id, user.id)
    rows = await diff_repo.list_for_session(session, session_id)
    if status_filter is not None:
        rows = [r for r in rows if r.status == status_filter]
    include_hunks = include == "hunks"
    return [_diff_summary(r, include_hunks=include_hunks) for r in rows]
