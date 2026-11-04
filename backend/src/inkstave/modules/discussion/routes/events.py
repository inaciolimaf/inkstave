"""The project event stream route (spec 117): one Server-Sent Events connection per open project."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from inkstave.core.db.session import UNIT_OF_WORK, get_session_factory
from inkstave.core.deps import get_redis, get_settings_dep
from inkstave.core.errors import ErrorEnvelope
from inkstave.modules.auth import sse_user
from inkstave.modules.discussion.events.stream import project_events_stream
from inkstave.modules.projects import ProjectNotFoundError, role_for

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from inkstave.core.config.settings import Settings
    from inkstave.modules.auth import User

router = APIRouter(prefix="/projects/{project_id}", tags=["events"])


@router.get(
    "/events",
    summary="Live project events (Server-Sent Events)",
    responses={404: {"model": ErrorEnvelope}},
)
async def project_events(
    project_id: UUID,
    user: User = Depends(sse_user),
    session: AsyncSession = UNIT_OF_WORK,
    sessions: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
    settings: Settings = Depends(get_settings_dep),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    # EventSource cannot send headers, so the token comes from ?access_token= (sse_user) and
    # the membership is checked here. Any active member may read: the route is not capability-gated.
    if await role_for(session, user.id, project_id) is None:
        raise ProjectNotFoundError()

    async def is_member() -> bool:
        # Runs inside the stream, after the request's unit of work has closed.
        async with sessions() as stream_session:
            return await role_for(stream_session, user.id, project_id) is not None

    return StreamingResponse(
        project_events_stream(redis, project_id, is_member, settings.project_events_keepalive_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
