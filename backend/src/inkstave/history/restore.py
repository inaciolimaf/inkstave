"""Restore service (spec 37): replays a past version as a *new* server-originated edit.

Restores are **non-destructive** — they reconstruct the target text and apply it to
the authoritative pycrdt document as one transaction, which broadcasts to clients,
persists, and is captured by spec 36 as a brand-new version. No history row is ever
deleted or rewritten. If the live room cannot be reached, the restore is atomic: it
fails with 409 and changes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import func, select

from inkstave.collab.protocol import encode_update
from inkstave.db.models.history import HistoryUpdate
from inkstave.errors import AppError
from inkstave.history.labels import create_doc_label, ensure_label_available
from inkstave.history.reconstruct import reconstruct_state, text_from_state
from inkstave.schemas.history import (
    DocRestoreResult,
    LabelRead,
    ProjectRestoreResponse,
    RestoreResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.collab.ws.components import CollabComponents
    from inkstave.storage.base import ObjectStore


class RoomUnreachableError(AppError):
    status_code = 409
    error_type = "room_unreachable"

    def __init__(self) -> None:
        super().__init__("The live document could not be reached; restore was not applied.")


async def _max_version(session: AsyncSession, doc_id: UUID) -> int:
    value = await session.scalar(
        select(func.max(HistoryUpdate.version)).where(HistoryUpdate.doc_id == doc_id)
    )
    return int(value) if value is not None else 0


async def restore_document(
    session: AsyncSession,
    components: CollabComponents | None,
    store: ObjectStore,
    *,
    project_id: UUID,
    doc_id: UUID,
    target_version: int,
    author_id: UUID | None,
    label_name: str | None = None,
) -> RestoreResponse:
    if components is None or components.history is None:
        raise RoomUnreachableError()

    # Reconstruct the target version's text (raises HistoryVersionNotFound -> 404).
    target_text = text_from_state(await reconstruct_state(session, store, doc_id, target_version))

    # Fail fast on a duplicate label name *before* mutating the live doc, so a doomed
    # restore changes nothing (spec 40 — restore atomicity).
    if label_name:
        await ensure_label_available(session, doc_id=doc_id, name=label_name)

    origin = f"restore-{uuid4().hex}"
    try:
        update = await components.manager.apply_server_update(doc_id, target_text, origin)
    except Exception as exc:  # the authoritative room could not be mutated
        raise RoomUnreachableError() from exc

    # Capture the restore as a brand-new version, authored by the restoring user.
    await components.history.capture_update(
        project_id=project_id,
        doc_id=doc_id,
        update=update,
        author_id=author_id,
        at=datetime.now(UTC),
    )
    await components.history.flush_doc(doc_id=doc_id, reason="manual")
    new_version = await _max_version(session, doc_id)

    label = None
    if label_name:
        row = await create_doc_label(
            session,
            project_id=project_id,
            doc_id=doc_id,
            version=new_version,
            name=label_name,
            created_by=author_id,
        )
        label = LabelRead.model_validate(row)

    # Broadcast LAST: only after the new version is recorded (and labelled), so clients
    # never observe a restore that failed to persist to history (spec 40).
    await components.redis_bridge.publish(doc_id, origin, encode_update(update))

    return RestoreResponse(
        doc_id=doc_id,
        restored_from_version=target_version,
        new_version=new_version,
        label=label,
    )


async def restore_project(
    session: AsyncSession,
    components: CollabComponents | None,
    store: ObjectStore,
    *,
    project_id: UUID,
    markers: dict[str, int],
    author_id: UUID | None,
) -> ProjectRestoreResponse:
    """Restore each document in a project-level label's `{doc_id: version}` map.

    Each doc restore is independent and non-destructive; a later doc's failure does
    not roll back already-restored docs.
    """
    results: list[DocRestoreResult] = []
    for doc_id_str, version in markers.items():
        doc_id = UUID(doc_id_str)
        if version < 1:
            results.append(
                DocRestoreResult(doc_id=doc_id, status="skipped", reason="no history at label")
            )
            continue
        try:
            res = await restore_document(
                session,
                components,
                store,
                project_id=project_id,
                doc_id=doc_id,
                target_version=version,
                author_id=author_id,
            )
            results.append(
                DocRestoreResult(doc_id=doc_id, status="restored", new_version=res.new_version)
            )
        except Exception as exc:  # noqa: BLE001 — report, do not abort the sweep
            results.append(DocRestoreResult(doc_id=doc_id, status="error", reason=str(exc)))
    return ProjectRestoreResponse(results=results)
