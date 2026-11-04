"""Authorization for the Git routes (spec 121 §5.3): HTTP Basic with a personal access token.

The token is the password; the user name is ignored. Session JWTs are not accepted here, and Git tokens are
not accepted anywhere else. Failed attempts are counted per client IP against ``RATE_LIMIT_GIT_AUTH``. A
non-member gets 404, a member without the capability gets 403.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import Request
from redis.asyncio import Redis

from inkstave.core.config.settings import Settings
from inkstave.core.errors import RateLimitError
from inkstave.modules.auth.models.user import User
from inkstave.modules.auth.throttling.limiter import client_ip, hit_window, parse_rate_limit
from inkstave.modules.git.auth.tokens import authenticate, basic_password
from inkstave.modules.git.errors import GitDisabledError, GitUnauthorizedError
from inkstave.modules.git.models import GitAccessToken
from inkstave.modules.projects import Capability, ProjectNotFoundError, capabilities_for, role_for
from inkstave.modules.projects.access.service import InsufficientRoleError
from inkstave.modules.projects.models.membership import MembershipRole

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class GitCaller:
    user: User
    token: GitAccessToken
    role: MembershipRole


READ_CAPABILITIES = frozenset({Capability.DOC_READ})
WRITE_CAPABILITIES = frozenset({Capability.DOC_WRITE, Capability.FILE_WRITE})


def _failure_key(request: Request, settings: Settings) -> str:
    return f"rl:git_auth:{client_ip(request, settings)}"


async def _check_not_throttled(redis: Redis, request: Request, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return
    limit, _ = parse_rate_limit(settings.rate_limit_git_auth)
    key = _failure_key(request, settings)
    failures = int(await redis.get(key) or 0)
    if failures >= limit:
        retry = await redis.ttl(key)
        raise RateLimitError(retry if retry > 0 else 1)


async def _count_failure(redis: Redis, request: Request, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return
    _, window = parse_rate_limit(settings.rate_limit_git_auth)
    await hit_window(redis, _failure_key(request, settings), window)


async def authorize_git(
    *,
    request: Request,
    session: AsyncSession,
    redis: Redis,
    settings: Settings,
    project_id: UUID,
    needed: frozenset[Capability],
) -> GitCaller:
    if not settings.git_enabled:
        raise GitDisabledError()
    await _check_not_throttled(redis, request, settings)
    password = basic_password(request.headers.get("authorization"))
    found = await authenticate(session, password) if password else None
    if found is None:
        await _count_failure(redis, request, settings)
        raise GitUnauthorizedError()
    user, token = found
    role = await role_for(session, user.id, project_id)
    if role is None:
        raise ProjectNotFoundError()
    granted = capabilities_for(role, compile_for_viewers=settings.compile_allowed_for_viewers)
    if not needed <= granted:
        raise InsufficientRoleError()
    return GitCaller(user=user, token=token, role=role)
