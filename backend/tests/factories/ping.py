"""Factory for the ``Ping`` example model."""

from __future__ import annotations

import itertools
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.ping import Ping


class PingFactory:
    """Builds :class:`Ping` instances with unique default notes."""

    _seq = itertools.count(1)

    @classmethod
    def build(cls, **kwargs: Any) -> Ping:
        kwargs.setdefault("note", f"ping-{next(cls._seq)}")
        return Ping(**kwargs)

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> Ping:
        ping = cls.build(**kwargs)
        session.add(ping)
        await session.flush()
        return ping
