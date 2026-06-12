"""Per-user in-app notification service (spec 39).

All mutating methods enforce that the notification belongs to the user (else 404).
Listing excludes dismissed and expired rows; ``sweep_expired`` hard-deletes expired
rows and is safe to re-run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import delete, func, select, update

from inkstave.db.models.notification import Notification
from inkstave.errors import NotFoundError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class NotificationNotFoundError(NotFoundError):
    error_type = "notification_not_found"

    def __init__(self) -> None:
        super().__init__("Notification not found.")


def _now() -> datetime:
    return datetime.now(UTC)


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: UUID,
        type: str,
        payload: dict[str, Any],
        expires_at: datetime | None = None,
        dedupe_on: tuple[str, str] | None = None,
    ) -> Notification:
        if dedupe_on is not None:
            key, value = dedupe_on
            existing = await self._session.scalar(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.type == type,
                    Notification.dismissed_at.is_(None),
                    Notification.payload[key].astext == value,
                )
            )
            if existing is not None:
                existing.payload = payload
                existing.expires_at = expires_at
                existing.read_at = None
                # Resurface a re-issued notification to the top of the list (spec 40).
                existing.created_at = _now()
                await self._session.flush()
                return existing

        notification = Notification(
            user_id=user_id, type=type, payload=payload, expires_at=expires_at
        )
        self._session.add(notification)
        await self._session.flush()
        return notification

    def _active(self, user_id: UUID, now: datetime) -> Any:
        return (
            (Notification.user_id == user_id)
            & Notification.dismissed_at.is_(None)
            & ((Notification.expires_at.is_(None)) | (Notification.expires_at > now))
        )

    async def list_active(
        self, *, user_id: UUID, limit: int = 50, before: datetime | None = None
    ) -> list[Notification]:
        now = _now()
        stmt = select(Notification).where(self._active(user_id, now))
        if before is not None:
            stmt = stmt.where(Notification.created_at < before)
        stmt = stmt.order_by(Notification.created_at.desc()).limit(limit)
        return list((await self._session.execute(stmt)).scalars())

    async def unread_count(self, *, user_id: UUID) -> int:
        now = _now()
        value = await self._session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(self._active(user_id, now), Notification.read_at.is_(None))
        )
        return int(value or 0)

    async def mark_read(self, *, user_id: UUID, notification_id: UUID) -> Notification:
        notification = await self._owned(user_id, notification_id)
        if notification.read_at is None:
            notification.read_at = _now()
            await self._session.flush()
        return notification

    async def mark_all_read(self, *, user_id: UUID) -> int:
        now = _now()
        result = await self._session.execute(
            update(Notification)
            .where(self._active(user_id, now), Notification.read_at.is_(None))
            .values(read_at=now)
        )
        await self._session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def dismiss(self, *, user_id: UUID, notification_id: UUID) -> None:
        notification = await self._owned(user_id, notification_id)
        if notification.dismissed_at is None:
            notification.dismissed_at = _now()
            await self._session.flush()

    async def sweep_expired(self, *, now: datetime | None = None) -> int:
        cutoff = now or _now()
        result = await self._session.execute(
            delete(Notification).where(
                Notification.expires_at.is_not(None), Notification.expires_at <= cutoff
            )
        )
        await self._session.flush()
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def _owned(self, user_id: UUID, notification_id: UUID) -> Notification:
        notification = await self._session.scalar(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        )
        if notification is None:
            raise NotificationNotFoundError()
        return notification
