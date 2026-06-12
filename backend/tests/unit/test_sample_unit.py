"""Sample unit test proving the unit tier runs (no DB, no app, no network)."""

from __future__ import annotations

from inkstave.db.models.ping import Ping
from tests.factories import PingFactory


def test_ping_factory_builds_unique_unsaved_instances() -> None:
    first = PingFactory.build()
    second = PingFactory.build()
    assert isinstance(first, Ping)
    assert isinstance(second, Ping)
    assert first.note != second.note


def test_ping_factory_respects_overrides() -> None:
    ping = PingFactory.build(note="custom")
    assert ping.note == "custom"
