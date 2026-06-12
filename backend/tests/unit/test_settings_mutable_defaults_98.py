"""Settings mutable defaults are explicit factories (spec 98).

Documents that the four converted fields keep their exact default values, that two
independent settings instances get non-aliased mutable objects (Pydantic v2
deep-copies the factory output), and that env-var override parsing is unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

from inkstave.agent.settings import AgentSettings
from inkstave.config import Settings

_EXTS = [
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".bib",
    ".tex", ".cls", ".sty", ".svg", ".eps", ".csv", ".txt",
]  # fmt: skip
_MIME = [
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf", "text/plain", "application/x-bibtex", "text/x-bibtex",
]  # fmt: skip
_COST = {"openai/gpt-4o-mini": {"input": 0.00015, "output": 0.0006}}


def _settings(**over: Any) -> Settings:
    base = {"jwt_secret": "x" * 40, "redis_url": "redis://redis:6379/0"}
    return Settings(**{**base, **over})  # type: ignore[arg-type]


def test_defaults_preserved() -> None:
    s = _settings()
    assert s.jwt_secret_previous == []
    assert s.upload_allowed_extensions == _EXTS
    assert s.allowed_upload_mime == _MIME
    assert AgentSettings().agent_model_cost_table == _COST


def test_mutable_defaults_are_not_aliased() -> None:
    a, b = _settings(), _settings()
    assert a.upload_allowed_extensions is not b.upload_allowed_extensions
    assert a.allowed_upload_mime is not b.allowed_upload_mime
    assert a.jwt_secret_previous is not b.jwt_secret_previous

    a.upload_allowed_extensions.append(".zzz")
    a.jwt_secret_previous.append("leaked")
    assert ".zzz" not in b.upload_allowed_extensions
    assert b.jwt_secret_previous == []

    ag1, ag2 = AgentSettings(), AgentSettings()
    assert ag1.agent_model_cost_table is not ag2.agent_model_cost_table
    ag1.agent_model_cost_table["extra/model"] = {"input": 9.0, "output": 9.0}
    assert "extra/model" not in ag2.agent_model_cost_table


def test_list_env_override_still_parses() -> None:
    # NoDecode + the config.py `_parse_str_list` validator: CSV and JSON still parse.
    s = _settings(
        upload_allowed_extensions=".a,.b",
        jwt_secret_previous='["s1","s2"]',
        allowed_upload_mime="text/plain",
    )
    assert s.upload_allowed_extensions == [".a", ".b"]
    assert s.jwt_secret_previous == ["s1", "s2"]
    assert s.allowed_upload_mime == ["text/plain"]


def test_agent_cost_table_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODEL_COST_TABLE", '{"m/x": {"input": 1.0, "output": 2.0}}')
    assert AgentSettings().agent_model_cost_table == {"m/x": {"input": 1.0, "output": 2.0}}
