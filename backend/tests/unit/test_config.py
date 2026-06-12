"""Unit tests for settings loading and caching."""

from __future__ import annotations

import pytest

from inkstave.config import Settings, get_settings


def test_defaults_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ["APP_NAME", "ENVIRONMENT", "CORS_ORIGINS", "LOG_LEVEL", "LOG_JSON"]:
        monkeypatch.delenv(var, raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app_name == "Inkstave"
    assert settings.environment == "dev"
    assert settings.debug is False
    assert settings.log_json is True
    assert settings.docs_enabled is True
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.request_id_header == "X-Request-ID"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DOCS_ENABLED", "false")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"
    assert settings.docs_enabled is False


def test_cors_origins_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", '["http://x.com", "http://y.com"]')
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == ["http://x.com", "http://y.com"]


def test_cors_origins_empty_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.cors_origins == []


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
