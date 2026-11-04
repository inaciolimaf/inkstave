"""Comment notifications (spec 118): bell rows for mentions and replies.

The discussion module decides who is notified and builds the payload; this hook only writes the
inbox rows, in the caller's unit of work. The e-mail for a mention is sent by the caller after the
commit, so it is not part of this hook.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from inkstave.modules.notifications.inbox.service import NotificationService
from inkstave.modules.notifications.models import NotificationType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.ext.asyncio import AsyncSession


async def notify_comment_users(
    session: AsyncSession,
    *,
    notification_type: NotificationType,
    user_ids: Iterable[UUID],
    payload: dict[str, Any],
) -> None:
    """One ``comment_mention`` or ``comment_reply`` row per user; the payload is shared."""
    service = NotificationService(session)
    for user_id in user_ids:
        await service.create(user_id=user_id, notification_type=notification_type, payload=payload)
