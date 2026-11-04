"""The ``user_dictionary_words`` table: a user's personal spell-check dictionary (spec 113).

Mapped as a Core table, not an ORM class: the case-insensitive key is an expression
(``lower(word)``), and PostgreSQL does not allow an expression as a primary key, so the
key is a unique index instead. The service writes with explicit statements.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Table, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from inkstave.core.db.base import Base

user_dictionary_words = Table(
    "user_dictionary_words",
    Base.metadata,
    Column(
        "user_id",
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("word", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("uq_user_dictionary_words_user_lower_word", "user_id", text("lower(word)"), unique=True),
)
