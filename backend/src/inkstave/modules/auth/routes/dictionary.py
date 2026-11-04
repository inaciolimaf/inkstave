"""Personal spell-check dictionary routes (spec 113). Every route requires the current user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from inkstave.core.db.session import UNIT_OF_WORK
from inkstave.core.errors import ErrorEnvelope
from inkstave.modules.auth.accounts import dictionary
from inkstave.modules.auth.deps import get_current_user
from inkstave.modules.auth.models.user import User
from inkstave.modules.auth.schemas.dictionary import DictionaryList, DictionaryWordCreate, DictionaryWordRead

router = APIRouter(tags=["dictionary"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorEnvelope},
    status.HTTP_409_CONFLICT: {"model": ErrorEnvelope},
}


@router.get("/me/dictionary", response_model=DictionaryList, summary="List the personal dictionary")
async def list_dictionary(
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> DictionaryList:
    return DictionaryList(words=await dictionary.list_words(session, user.id))


@router.post(
    "/me/dictionary",
    status_code=status.HTTP_201_CREATED,
    response_model=DictionaryWordRead,
    summary="Add a word to the personal dictionary (idempotent)",
    responses=_ERRORS,
)
async def add_dictionary_word(
    data: DictionaryWordCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> DictionaryWordRead:
    await dictionary.add_word(session, user.id, data.word)
    return DictionaryWordRead(word=data.word)


@router.delete(
    "/me/dictionary/{word:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a word from the personal dictionary",
    responses=_ERRORS,
)
async def remove_dictionary_word(
    word: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = UNIT_OF_WORK,
) -> None:
    await dictionary.remove_word(session, user.id, word)
