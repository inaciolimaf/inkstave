"""Publishing a comment write after its commit: the event and the mention e-mails (spec 118).

The routes take a :class:`CommentPublisher` and hand it each :class:`CommentOutcome`. Both the event and the
e-mails are background tasks, which the framework runs after the unit of work has committed. A failed
enqueue is logged, not raised: the comment is already saved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

from fastapi import BackgroundTasks, Depends

from inkstave.core.deps import get_redis
from inkstave.infra.deps import get_email_enqueuer
from inkstave.modules.discussion.events.channel import schedule_project_event

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from inkstave.infra.mailer.enqueuer import EmailEnqueuer
    from inkstave.modules.discussion.comments.outcome import CommentOutcome, MentionMail

T = TypeVar("T")
logger = logging.getLogger("inkstave.discussion.comments")


async def _enqueue_quietly(enqueuer: EmailEnqueuer, mail: MentionMail) -> None:
    try:
        await enqueuer.enqueue_email(template="comment_mention", to=mail.to, context=mail.context)
    except Exception:
        logger.warning("comment mention e-mail could not be enqueued", exc_info=True)


@dataclass(frozen=True)
class CommentPublisher:
    background: BackgroundTasks
    redis: Redis
    enqueuer: EmailEnqueuer

    def emit(self, project_id: UUID, outcome: CommentOutcome[T]) -> T:
        """Schedule the outcome's event and e-mails after the commit, and return its result."""
        if outcome.event is not None:
            event_type, payload = outcome.event
            schedule_project_event(self.background, self.redis, project_id, event_type, payload)
        for mail in outcome.mails:
            self.background.add_task(_enqueue_quietly, self.enqueuer, mail)
        return outcome.result


async def get_comment_publisher(
    background: BackgroundTasks,
    redis: Redis = Depends(get_redis),
    enqueuer: EmailEnqueuer = Depends(get_email_enqueuer),
) -> CommentPublisher:
    return CommentPublisher(background=background, redis=redis, enqueuer=enqueuer)
