"""Shared helpers for the async compile API (spec 22/23).

Internal dependencies, errors and header/auth helpers extracted from
``compile.py`` to keep each module small. Nothing here affects the OpenAPI
schema — these are plain dependencies/helpers wired identically by the routes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import Depends, Query, status
from fastapi.security import HTTPAuthorizationCredentials

from inkstave.core.db.session import get_db_session
from inkstave.core.deps import get_settings_dep
from inkstave.core.errors import ErrorEnvelope, NotFoundError
from inkstave.infra.deps import get_object_store
from inkstave.modules.auth.credentials.tokens import TokenService
from inkstave.modules.auth.deps import NotAuthenticatedError, _resolve_user, bearer_scheme, get_token_service
from inkstave.modules.compile.outputs.repository import OutputRepository
from inkstave.modules.compile.outputs.store import OutputStore, StoredObject
from inkstave.modules.compile.queue.repository import CompileRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.core.config.settings import Settings
    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.auth.models.user import User

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_429_TOO_MANY_REQUESTS: {"model": ErrorEnvelope},
}


class CompileNotFoundError(NotFoundError):
    error_type = "compile_not_found"

    def __init__(self) -> None:
        super().__init__("Compile not found.")


def get_output_store(
    session: AsyncSession = Depends(get_db_session),
    store: ObjectStore = Depends(get_object_store),
    settings: Settings = Depends(get_settings_dep),
) -> OutputStore:
    return OutputStore(storage=store, repo=OutputRepository(session), settings=settings)


async def _require_compile(session: AsyncSession, project_id: UUID, compile_id: UUID) -> None:
    if await CompileRepository(session).get(project_id, compile_id) is None:
        raise CompileNotFoundError()


def _pdf_headers(obj: StoredObject, settings: Settings) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "ETag": obj.etag,
        "Cache-Control": f"private, max-age={settings.compile_pdf_cache_max_age_s}",
        "Content-Disposition": 'inline; filename="output.pdf"',
    }


async def _sse_user(
    access_token: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token_service: TokenService = Depends(get_token_service),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """SSE auth: token via the Authorization header **or** an ``?access_token=`` query."""
    token = (credentials.credentials if credentials else None) or access_token
    if not token:
        raise NotAuthenticatedError()
    return await _resolve_user(token, token_service, session)
