"""Environment / settings fixtures and autouse speed/network guards (spec 04).

These are registered as a pytest plugin from the root ``tests/conftest.py`` so
the autouse fixtures keep applying to every test in the suite.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.engine import make_url

from inkstave.config import Settings, get_settings
from inkstave.db.engine import normalize_async_dsn
from inkstave.logging import set_request_id
from tests.fixtures.paths import DEFAULT_TEST_DB

# --------------------------------------------------------------------------- #
# Environment / settings
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session", autouse=True)
def _configure_test_env() -> Iterator[None]:
    """Force test settings for the whole session.

    Points the app and Alembic at ``TEST_DATABASE_URL`` and selects readable,
    non-JSON logs. Individual unit tests may still construct ``Settings`` with
    explicit overrides (``_env_file=None`` + monkeypatched env).
    """
    test_db_url = normalize_async_dsn(os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB))
    # Under pytest-xdist (spec 53), each worker uses its own database (suffixed by the
    # worker id) so workers never share state and the per-test rollback stays isolated.
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        parsed = make_url(test_db_url)
        test_db_url = parsed.set(database=f"{parsed.database}_{worker}").render_as_string(
            hide_password=False
        )
    overrides = {
        "DATABASE_URL": test_db_url,
        "ENVIRONMENT": "test",
        # Spec 51 §5.6 mandates the test profile force LOG_LEVEL=warning (LOG_FORMAT=json,
        # OTEL_ENABLED=false, METRICS_PUBLIC=true already come from config defaults).
        "LOG_LEVEL": "WARNING",
        # Minimal argon2 cost so password hashing is sub-millisecond in tests.
        "ARGON2_TIME_COST": "1",
        "ARGON2_MEMORY_COST": "8",
        "ARGON2_PARALLELISM": "1",
        # Deterministic JWT signing secret for tests (spec 07).
        "JWT_SECRET": "test-secret-not-for-production-0123456789abcdef",
        # High rate limits by default (spec 08); the 429 test overrides these.
        "RATE_LIMIT_LOGIN": "1000/300",
        "RATE_LIMIT_REGISTER": "1000/3600",
        "RATE_LIMIT_REFRESH": "1000/300",
    }
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_request_state() -> Iterator[None]:
    """Clear cached settings + request-id context around every test."""
    get_settings.cache_clear()
    set_request_id(None)
    yield
    get_settings.cache_clear()
    set_request_id(None)


@pytest.fixture(autouse=True)
def _no_real_compile() -> Iterator[None]:
    """Hard speed-guard (spec 25): a real Tectonic compile must NEVER run in a
    fast tier. Replace ``LocalTectonicRunner.run`` with a loud failure so any
    test that forgets to inject a fake runner fails fast and explains itself,
    rather than silently spawning ``tectonic`` and blowing the time budget.

    The opt-in smoke tier sets ``RUN_REAL_COMPILE=1`` to run the single real
    compile; there the guard steps aside.
    """
    if os.environ.get("RUN_REAL_COMPILE") == "1":
        yield
        return

    from inkstave.compile.runner import LocalTectonicRunner

    async def _blocked(_self: object, **_kw: object) -> None:
        raise RuntimeError(
            "Real Tectonic compile invoked in a fast-tier test. Inject a fake "
            "runner (see tests' FakeRunner), or gate the test behind the smoke "
            "tier with RUN_REAL_COMPILE=1."
        )

    original = LocalTectonicRunner.run
    LocalTectonicRunner.run = _blocked  # type: ignore[method-assign]
    try:
        yield
    finally:
        LocalTectonicRunner.run = original  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _no_real_network() -> Iterator[None]:
    """Block outbound DNS for non-local hosts (spec 53): any accidental real network
    call (e.g. a real LLM HTTP request) fails fast. Localhost/IP literals — the test
    DB and fakeredis — are allowed; the opt-in smoke tier sets RUN_REAL_COMPILE=1.
    """
    if os.environ.get("RUN_REAL_COMPILE") == "1":
        yield
        return
    import socket

    allowed = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    db_host = make_url(os.environ.get("DATABASE_URL", "")).host
    if db_host:
        allowed.add(db_host)
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host: Any, *args: Any, **kwargs: Any) -> Any:
        name = host if isinstance(host, str) else ""
        is_ip = name.replace(".", "").isdigit() or ":" in name
        if name and name not in allowed and not is_ip:
            raise RuntimeError(
                f"Real network access to {host!r} blocked in a fast-tier test (spec 53). "
                "Stub the external call (FakeLLM / fake runner / mock transport)."
            )
        return real_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = guarded  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.getaddrinfo = real_getaddrinfo  # type: ignore[assignment]


@pytest.fixture
def settings_override() -> Settings:
    """The active test :class:`Settings` (environment=test, JSON logs off)."""
    return get_settings()
