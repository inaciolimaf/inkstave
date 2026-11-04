"""Wire shapes of the personal spell-check dictionary (spec 113)."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

from inkstave.core.schemas import StrictModel

WORD_MAX_LENGTH = 64
_WHITESPACE = re.compile(r"\s")


class DictionaryWordCreate(StrictModel):
    word: str = Field(min_length=1, max_length=WORD_MAX_LENGTH)

    @field_validator("word")
    @classmethod
    def _one_token(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("A dictionary word must not be blank.")
        if _WHITESPACE.search(stripped):
            raise ValueError("A dictionary word must not contain whitespace.")
        return stripped


class DictionaryWordRead(BaseModel):
    word: str


class DictionaryList(BaseModel):
    words: list[str]
