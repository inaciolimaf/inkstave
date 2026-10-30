"""`spawn` keeps fire-and-forget tasks alive and reports their failures."""

from __future__ import annotations

import asyncio
import logging

import pytest

from inkstave import background


async def test_spawn_holds_the_task_until_it_finishes() -> None:
    release = asyncio.Event()

    async def waits() -> None:
        await release.wait()

    task = background.spawn(waits(), name="held")
    assert task in background._running
    release.set()
    await task
    await asyncio.sleep(0)
    assert task not in background._running


async def test_spawn_logs_a_failure(caplog: pytest.LogCaptureFixture) -> None:
    async def fails() -> None:
        raise ValueError("boom")

    with caplog.at_level(logging.ERROR, logger="inkstave.background"):
        task = background.spawn(fails(), name="doomed")
        await asyncio.wait([task])
        await asyncio.sleep(0)

    assert "background task doomed failed" in caplog.text
    assert "boom" in caplog.text


async def test_spawn_does_not_report_cancellation(caplog: pytest.LogCaptureFixture) -> None:
    async def waits() -> None:
        await asyncio.Event().wait()

    task = background.spawn(waits(), name="cancelled")
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.wait([task])
    await asyncio.sleep(0)

    assert task not in background._running
    assert "cancelled" not in caplog.text
