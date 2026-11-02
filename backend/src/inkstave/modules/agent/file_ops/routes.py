"""Routes where the user reads and decides the file operations the agent proposed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.errors import AppError, ErrorEnvelope, NotFoundError
from inkstave.infra.deps import get_object_store
from inkstave.modules.agent.access import owned_session, require_member
from inkstave.modules.agent.file_ops import repo
from inkstave.modules.agent.file_ops.apply import apply_file_op, reject_file_op
from inkstave.modules.agent.file_ops.models import ProposedFileOp
from inkstave.modules.agent.file_ops.schemas import ProposedFileOpOut
from inkstave.modules.agent.safety import AgentAuditAction, AuditSubject, audit
from inkstave.modules.auth import get_current_user
from inkstave.modules.projects import Capability, capabilities_for, role_for

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.infra.storage.base import ObjectStore
    from inkstave.modules.auth import User

router = APIRouter(prefix="/projects/{project_id}/agent/sessions/{session_id}/file-ops", tags=["agent"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_403_FORBIDDEN: {"model": ErrorEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


class FileOpNotFoundError(NotFoundError):
    error_type = "file_op_not_found"

    def __init__(self) -> None:
        super().__init__("This proposal does not exist.")


class FileOpForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    error_type = "file_op_forbidden"

    def __init__(self) -> None:
        super().__init__("Applying a proposal requires editor access.")


async def _decidable_op(
    db: AsyncSession, project_id: UUID, session_id: UUID, op_id: UUID, user: User
) -> ProposedFileOp:
    """The open row, after checking the caller may change this project *now*."""
    await require_member(db, project_id, user.id)
    await owned_session(db, project_id, session_id, user.id)
    if Capability.DOC_WRITE not in capabilities_for(await role_for(db, user.id, project_id)):
        raise FileOpForbiddenError()
    op = await repo.get_for_session(db, session_id, op_id)
    if op is None:
        raise FileOpNotFoundError()
    return op


@router.get("", response_model=list[ProposedFileOpOut], responses=_ERRORS)
async def list_file_ops(
    project_id: UUID,
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = UNIT_OF_WORK,
) -> list[ProposedFileOpOut]:
    await require_member(db, project_id, user.id)
    await owned_session(db, project_id, session_id, user.id)
    return [ProposedFileOpOut.model_validate(r) for r in await repo.list_for_session(db, session_id)]


@router.post("/{op_id}/apply", response_model=ProposedFileOpOut, responses=_ERRORS)
async def apply_op(
    project_id: UUID,
    session_id: UUID,
    op_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = UNIT_OF_WORK,
    store: ObjectStore = Depends(get_object_store),
) -> ProposedFileOpOut:
    op = await _decidable_op(db, project_id, session_id, op_id, user)
    await apply_file_op(db, op, store=store)
    subject = AuditSubject(user.id, project_id, session_id, None)
    detail = {"file_op_id": str(op.id), "kind": op.kind, "path": op.path}
    await audit(db, AgentAuditAction.apply_recorded, subject, detail=detail)
    return ProposedFileOpOut.model_validate(op)


@router.post("/{op_id}/reject", response_model=ProposedFileOpOut, responses=_ERRORS)
async def reject_op(
    project_id: UUID,
    session_id: UUID,
    op_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = UNIT_OF_WORK,
) -> ProposedFileOpOut:
    op = await _decidable_op(db, project_id, session_id, op_id, user)
    await reject_file_op(db, op)
    return ProposedFileOpOut.model_validate(op)
