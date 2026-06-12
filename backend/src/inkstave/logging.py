"""Structured logging configuration and request-id propagation.

A request id is stored in a :class:`~contextvars.ContextVar` by the
:class:`~inkstave.middleware.RequestIdMiddleware` and injected into every log
record by :class:`RequestIdFilter`, so logs emitted anywhere during a request
carry its correlation id.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from pythonjsonlogger.json import JsonFormatter

from inkstave.observability.context import request_id_var as request_id_ctx

if TYPE_CHECKING:
    from inkstave.config import Settings

# `request_id_ctx` is the shared observability context var (spec 51) so ids set here
# and by the RequestContextMiddleware correlate through one source of truth.


def get_request_id() -> str | None:
    """Return the current request's correlation id, if any."""
    return request_id_ctx.get()


def set_request_id(request_id: str | None) -> None:
    """Bind ``request_id`` to the current context."""
    request_id_ctx.set(request_id)


class RequestIdFilter(logging.Filter):
    """Attach the current ``request_id`` to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def build_formatter(log_json: bool) -> logging.Formatter:
    """Build the JSON or console formatter used by the root handler."""
    if log_json:
        return JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
            timestamp=False,
        )
    return logging.Formatter("%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s")


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once, idempotently.

    Replaces any existing handlers with a single stdout handler using the
    configured formatter, and attaches the request-id filter.
    """
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    # Drop handlers from any previous call so repeated create_app() in tests
    # does not stack duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(build_formatter(settings.log_json))
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)
