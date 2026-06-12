"""Unit tests for observability: redaction, formatter, context, metrics (spec 51)."""

from __future__ import annotations

import importlib
import json
import logging

import pytest
from fastapi import FastAPI
from prometheus_client import REGISTRY

from inkstave.observability import metrics
from inkstave.observability.context import bind_context, clear_context, current_context
from inkstave.observability.log import JsonLogFormatter, redact
from inkstave.observability.metrics import track_job, track_ws
from inkstave.observability.middleware import _UNMATCHED, _route_template


def _record(name: str = "test.logger", msg: str = "hi", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(name, logging.INFO, "f.py", 1, msg, None, None)
    record.__dict__.update(extra)
    return record


# --- redaction (AC4) -------------------------------------------------------- #


def test_redact_removes_denylisted_keys_case_insensitive_and_nested() -> None:
    out = redact(
        {
            "password": "p",
            "Authorization": "Bearer t",
            "openrouter_api_key": "k",
            "Set-Cookie": "c",
            "nested": {"hashed_password": "h", "safe": "ok"},
            "tokens_prompt": 5,
            "request_id": "r1",
        }
    )
    assert out["password"] == "***REDACTED***"
    assert out["Authorization"] == "***REDACTED***"
    assert out["openrouter_api_key"] == "***REDACTED***"
    assert out["Set-Cookie"] == "***REDACTED***"
    assert out["nested"]["hashed_password"] == "***REDACTED***"
    assert out["nested"]["safe"] == "ok"
    assert out["tokens_prompt"] == 5  # benign keys are not false-positived
    assert out["request_id"] == "r1"


# --- JSON formatter (AC1, AC4) ---------------------------------------------- #


def test_formatter_emits_single_line_json_with_schema_and_context() -> None:
    fmt = JsonLogFormatter(service="inkstave-backend", env="test", log_stacks=True)
    tokens = bind_context(request_id="r1", user_id="u1")
    try:
        line = fmt.format(_record(**{"http.method": "GET", "password": "secret"}))
    finally:
        clear_context(tokens)

    assert "\n" not in line
    data = json.loads(line)
    for field in ("timestamp", "level", "logger", "message", "service", "env"):
        assert field in data
    assert data["level"] == "info" and data["logger"] == "test.logger"
    assert data["service"] == "inkstave-backend" and data["env"] == "test"
    assert data["request_id"] == "r1" and data["user_id"] == "u1"
    assert data["http.method"] == "GET"
    assert data["password"] == "***REDACTED***"  # redacted even via call-site extra
    assert data["timestamp"].endswith("Z")


def test_formatter_omits_unbound_context_fields() -> None:
    fmt = JsonLogFormatter(service="s", env="test", log_stacks=False)
    data = json.loads(fmt.format(_record()))
    assert "request_id" not in data and "user_id" not in data  # no null spam


# --- request context (AC3) -------------------------------------------------- #


def test_bind_and_clear_context_no_leak_between_requests() -> None:
    t1 = bind_context(request_id="a", user_id="u")
    assert current_context() == {"request_id": "a", "user_id": "u"}
    clear_context(t1)
    assert current_context() == {}  # fully reset — nothing leaks to the next "request"

    t2 = bind_context(request_id="b")
    assert current_context() == {"request_id": "b"}  # no stale user_id from before
    clear_context(t2)


# --- metric helpers (AC11) -------------------------------------------------- #


def test_metrics_module_reimport_does_not_raise() -> None:
    importlib.reload(metrics)  # guarded registry: re-registration must not explode
    assert metrics.http_requests is not None


async def test_track_job_records_status_even_on_exception() -> None:
    base = (
        REGISTRY.get_sample_value(
            "inkstave_job_duration_seconds_count", {"job_name": "t", "status": "error"}
        )
        or 0.0
    )
    with pytest.raises(RuntimeError):
        async with track_job("t"):
            raise RuntimeError("boom")
    after = REGISTRY.get_sample_value(
        "inkstave_job_duration_seconds_count", {"job_name": "t", "status": "error"}
    )
    assert after == base + 1


def test_track_ws_gauge_returns_to_baseline_on_exception() -> None:
    sample = lambda: (  # noqa: E731
        REGISTRY.get_sample_value("inkstave_ws_connections_active", {"kind": "collab"}) or 0.0
    )
    before = sample()
    with pytest.raises(ValueError), track_ws("collab"):
        assert sample() == before + 1  # raised by 1 inside
        raise ValueError("handler crashed")
    assert sample() == before  # decremented in finally


# --- route-template extraction (AC: spec 51 §8) ----------------------------- #


def _scope(app: FastAPI, method: str, path: str) -> dict[str, object]:
    """A minimal ASGI HTTP scope sufficient for `_route_template` matching."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "app": app,
    }


def _template_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/projects/{project_id}")
    async def _project(project_id: str) -> dict[str, str]:  # pragma: no cover - never called
        return {"project_id": project_id}

    return app


def test_route_template_returns_parameterized_template_for_matched_route() -> None:
    app = _template_app()
    template = _route_template(
        _scope(app, "GET", "/api/v1/projects/123e4567-e89b-12d3-a456-426614174000")
    )
    # The bounded template — not the concrete path — keeps metric cardinality low.
    assert template == "/api/v1/projects/{project_id}"


def test_route_template_returns_unmatched_for_unknown_path() -> None:
    app = _template_app()
    assert _route_template(_scope(app, "GET", "/api/v1/does-not-exist")) == _UNMATCHED


def test_agent_token_helper_increments_with_model_allowlist() -> None:
    base = (
        REGISTRY.get_sample_value(
            "inkstave_agent_tokens_total", {"direction": "prompt", "model": "openai/gpt-4o-mini"}
        )
        or 0.0
    )
    metrics.inc_agent_tokens("prompt", "openai/gpt-4o-mini", 12)
    after = REGISTRY.get_sample_value(
        "inkstave_agent_tokens_total", {"direction": "prompt", "model": "openai/gpt-4o-mini"}
    )
    assert after == base + 12
    # An unknown model is bucketed to "other" to bound cardinality.
    metrics.inc_agent_tokens("prompt", "some/private-model", 3)
    assert (
        REGISTRY.get_sample_value(
            "inkstave_agent_tokens_total", {"direction": "prompt", "model": "other"}
        )
        is not None
    )
