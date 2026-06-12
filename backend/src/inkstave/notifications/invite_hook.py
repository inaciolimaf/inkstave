"""Invite → notification + email hook (spec 39, §5.2.6).

Additive to spec 33's invite flow: when an invite is created, create an in-app
``project_invite`` notification for the invitee *if they already have an account*
(de-duped per invite), and **always** enqueue the invite email.

NOTE (spec 68 #126): spec 33 originally specified only a no-op invite-email stub;
the real spec-39 email pipeline was delivered early and supersedes that stub.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from inkstave.db.models.user import User
from inkstave.notifications.service import NotificationService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from inkstave.config import Settings
    from inkstave.db.models.invite import ProjectInvite
    from inkstave.mailer.enqueuer import EmailEnqueuer


async def notify_invite(
    session: AsyncSession,
    email_enqueuer: EmailEnqueuer,
    settings: Settings,
    *,
    invite: ProjectInvite,
    raw_token: str,
    project_name: str,
    inviter_name: str,
) -> None:
    # Spec 33 §5.5 / FRONTEND_URL is the documented base for invite accept links
    # (the SPA route ``/invite/{token}``); use it rather than app_base_url (spec 68 #127).
    accept_url = f"{settings.frontend_url.rstrip('/')}/invite/{raw_token}"

    invitee = await session.scalar(
        select(User).where(func.lower(User.email) == invite.email.strip().lower())
    )
    if invitee is not None:
        await NotificationService(session).create(
            user_id=invitee.id,
            type="project_invite",
            payload={
                "project_id": str(invite.project_id),
                "project_name": project_name,
                "inviter_name": inviter_name,
                "role": invite.role,
                "invite_id": str(invite.id),
                "accept_url": accept_url,
            },
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.notification_invite_ttl_days),
            dedupe_on=("invite_id", str(invite.id)),
        )

    await email_enqueuer.enqueue_email(
        template="project_invite",
        to=invite.email,
        context={
            "project_name": project_name,
            "inviter_name": inviter_name,
            "role": invite.role,
            "accept_url": accept_url,
        },
    )
