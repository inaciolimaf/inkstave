"""Unit tests for LogProblemsService: truncation, caps, counts, no-log (spec 27)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from inkstave.config import Settings
from inkstave.logparse.models import ProblemSeverity
from inkstave.logparse.service import LogNotAvailable, LogProblemsService
from tests.logparse_fixtures import SAMPLE_LOG


class _Row:
    def __init__(self) -> None:
        self.id = uuid4()
        self.main_file = "main.tex"


class _FakeRepo:
    def __init__(self, row: _Row | None) -> None:
        self._row = row

    async def get(self, project_id: object, compile_id: object) -> _Row | None:
        return self._row

    async def get_latest(self, project_id: object) -> _Row | None:
        return self._row


class _FakeStored:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.size = len(data)
        self.etag = "e"

    async def stream(self) -> AsyncIterator[bytes]:
        yield self._data


class _FakeStore:
    def __init__(self, obj: _FakeStored | None) -> None:
        self._obj = obj

    async def open_log(self, compile_id: object) -> _FakeStored | None:
        return self._obj


def _settings(**over: object) -> Settings:
    return Settings(_env_file=None, **over)  # type: ignore[call-arg]


def _service(log: bytes | None, **over: object) -> LogProblemsService:
    store = _FakeStore(_FakeStored(log) if log is not None else None)
    return LogProblemsService(
        repo=_FakeRepo(_Row()),  # type: ignore[arg-type]
        output_store=store,  # type: ignore[arg-type]
        settings=_settings(**over),
    )


async def test_counts_match_severities() -> None:
    result = await _service(SAMPLE_LOG.encode()).problems_for(uuid4(), None)
    assert result.errors == 1
    assert result.warnings == 2
    assert result.infos == 1
    assert len(result.problems) == 4


async def test_no_log_raises() -> None:
    with pytest.raises(LogNotAvailable):
        await _service(None).problems_for(uuid4(), None)


async def test_truncation_emits_synthetic_info() -> None:
    big = ("x" * 100 + "\n").encode() * 50
    result = await _service(big, logparse_max_log_bytes=64).problems_for(uuid4(), None)
    assert result.problems[0].rule == "log-truncated"
    assert result.problems[0].severity is ProblemSeverity.info


async def test_max_problems_cap_appends_omitted_info() -> None:
    result = await _service(SAMPLE_LOG.encode(), logparse_max_problems=1).problems_for(
        uuid4(), None
    )
    assert len(result.problems) == 2  # 1 kept + the synthetic notice
    assert result.problems[-1].rule == "too-many-problems"
