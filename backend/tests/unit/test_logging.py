"""Unit tests for JSON logging and request-id propagation."""

from __future__ import annotations

import io
import json
import logging

from inkstave.logging import RequestIdFilter, build_formatter, set_request_id


def _emit_one(message: str) -> str:
    logger = logging.getLogger("inkstave.test.logging")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(build_formatter(log_json=True))
    handler.addFilter(RequestIdFilter())
    logger.addHandler(handler)

    logger.info(message)
    return stream.getvalue().strip()


def test_json_log_contains_required_keys() -> None:
    set_request_id("req-abc")
    payload = json.loads(_emit_one("hello world"))
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-abc"
    assert "timestamp" in payload
    set_request_id(None)


def test_request_id_absent_outside_context() -> None:
    set_request_id(None)
    payload = json.loads(_emit_one("no context"))
    assert payload["request_id"] is None
