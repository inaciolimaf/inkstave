"""Factory for the ``User`` model."""

from __future__ import annotations

import itertools
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.db.models.user import User


class UserFactory:
    """Builds :class:`User` rows with unique default emails."""

    _seq = itertools.count(1)

    @classmethod
    def build(cls, **kwargs: Any) -> User:
        n = next(cls._seq)
        kwargs.setdefault("email", f"user{n}@example.com")
        # Placeholder hash for tests that only need a row to exist.
        kwargs.setdefault("hashed_password", "$argon2id$v=19$m=8,t=1,p=1$abc$def")
        kwargs.setdefault("display_name", f"User {n}")
        return User(**kwargs)

    @classmethod
    async def create(cls, session: AsyncSession, **kwargs: Any) -> User:
        user = cls.build(**kwargs)
        session.add(user)
        await session.flush()
        return user
