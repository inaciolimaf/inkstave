"""Shared test fixtures and harness — the testing foundation (spec 04).

Design goals (see docs/adr/0004-testing-foundation.md):

* **Fast.** ASGI-transport client (no sockets), a faked Redis, and a test
  database migrated **once per session** into a template, with each test wrapped
  in a transaction that is **rolled back** (no per-test schema rebuild, no
  cross-test state).
* **By convention.** Feature specs reuse these fixtures (`async_client`,
  `db_session`, `redis`, `settings_override`, `app`) and add factories under
  ``tests/factories/``.
* **No slow externals.** Tectonic and the LLM are never invoked; slow work lives
  in ARQ jobs whose bodies are mocked.

The fixtures themselves are grouped by domain under ``tests/fixtures/`` and
registered below with ``pytest_plugins`` so each module stays small. pytest only
auto-discovers fixtures from ``conftest.py`` files, so this registration is what
keeps every fixture available to all tests by the same name, scope, and autouse
behaviour. The failure-mode fake classes are re-exported here so existing
``from tests.conftest import Fake...`` imports keep working.
"""

from __future__ import annotations

from tests.fixtures.fakes import (
    FakeEngineBroken,
    FakeEngineOk,
    FakeRedisHanging,
    FakeRedisRaising,
    _FakeConnection,
)
from tests.fixtures.paths import ALEMBIC_INI as _ALEMBIC_INI
from tests.fixtures.paths import DEFAULT_TEST_DB as _DEFAULT_TEST_DB

# Register the per-domain fixture modules as pytest plugins. Listing them here
# (in the root conftest) is what makes their fixtures — including the autouse
# guards in ``env`` — apply to the whole test suite.
pytest_plugins = (
    "tests.fixtures.env",
    "tests.fixtures.database",
    "tests.fixtures.services",
)

__all__ = [
    "FakeEngineBroken",
    "FakeEngineOk",
    "FakeRedisHanging",
    "FakeRedisRaising",
    "_FakeConnection",
    "_ALEMBIC_INI",
    "_DEFAULT_TEST_DB",
]
