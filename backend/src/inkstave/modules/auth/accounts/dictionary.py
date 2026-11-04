"""Personal spell-check dictionary (spec 113): one list of words per user, matched without case.

Words are unique per user under ``lower(word)``. Adding a word that is already there is a no-op,
so the call is idempotent. The user row is locked while the count is checked, so two tabs cannot
push a user past the cap together.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.errors import ConflictError
from inkstave.modules.auth.models.user import User
from inkstave.modules.auth.models.user_dictionary_word import user_dictionary_words as words

MAX_WORDS = 5000


class DictionaryFullError(ConflictError):
    error_type = "dictionary_full"

    def __init__(self) -> None:
        super().__init__(f"The personal dictionary is full ({MAX_WORDS} words).")


async def list_words(session: AsyncSession, user_id: UUID) -> list[str]:
    rows = await session.execute(
        select(words.c.word).where(words.c.user_id == user_id).order_by(func.lower(words.c.word))
    )
    return [str(word) for word in rows.scalars()]


async def add_word(session: AsyncSession, user_id: UUID, word: str) -> None:
    # Serialise writers of this user's dictionary on the user row.
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    present = await session.scalar(
        select(exists().where(words.c.user_id == user_id, func.lower(words.c.word) == func.lower(word)))
    )
    if present:
        return
    count = await session.scalar(select(func.count()).select_from(words).where(words.c.user_id == user_id))
    if (count or 0) >= MAX_WORDS:
        raise DictionaryFullError()
    # ON CONFLICT DO NOTHING covers a concurrent insert of the same word that slipped past the check.
    await session.execute(pg_insert(words).values(user_id=user_id, word=word).on_conflict_do_nothing())


async def remove_word(session: AsyncSession, user_id: UUID, word: str) -> None:
    await session.execute(
        words.delete().where(words.c.user_id == user_id, func.lower(words.c.word) == func.lower(word))
    )
