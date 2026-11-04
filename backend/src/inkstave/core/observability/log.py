"""Structured JSON logging: schema, redaction, formatter, configuration (spec 51)."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from inkstave.core.observability.context import current_context

if TYPE_CHECKING:
    from inkstave.core.config.settings import Settings

# Substrings that mark a key as secret (case-insensitive). Chosen to cover the spec
# denylist (authorization, cookie/set-cookie, password/hashed_password, x-api-key,
# anthropic_api_key, openrouter_api_key) WITHOUT false-positiving on benign keys like ``tokens_prompt``.
_SECRET_SUBSTRINGS = (
    "password",
    "authorization",
    "secret",
    "api_key",
    "api-key",
    "access_key",  # e.g. s3_access_key_id (spec 52 added S3 creds; spec 55 closes the gap)
    "cookie",
)
_REDACTED = "***REDACTED***"

# Standard LogRecord attributes never emitted as their own JSON fields.
_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
    "color_message",
}


def _is_secret(key: str) -> bool:
    lowered = key.lower()
    return any(sub in lowered for sub in _SECRET_SUBSTRINGS)


# Bearer tokens carried in a URL: the token segment of /share-links/{token} and /invites/{token},
# and any ``token=`` query value. Matched on raw request paths, which the access log prints.
_TOKEN_IN_URL = re.compile(r"(/(?:share-links|invites)/)[^/?#\s\"]+|(\btoken=)[^&\s\"]+")


def redact_path(text: str) -> str:
    """Mask the token in a URL-like string (spec 116): the raw token never reaches a log line."""
    return _TOKEN_IN_URL.sub(lambda m: f"{m.group(1) or m.group(2)}{_REDACTED}", text)


class SecretPathFilter(logging.Filter):
    """Masks tokens in the arguments of a logger that prints request paths (uvicorn's access log)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact_path(a) if isinstance(a, str) else a for a in record.args)
        return True


def redact(value: Any) -> Any:
    """Recursively replace denylisted keys' values with a redaction marker."""
    if isinstance(value, dict):
        return {
            k: (_REDACTED if isinstance(k, str) and _is_secret(k) else redact(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class JsonLogFormatter(logging.Formatter):
    """One single-line JSON object per record, with the spec-51 field schema."""

    def __init__(self, *, service: str, env: str, log_stacks: bool) -> None:
        super().__init__()
        self.service = service
        self.env = env
        self.log_stacks = log_stacks

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
            "env": self.env,
        }
        data.update(current_context())  # request_id, trace_id, user_id, … when bound
        for key, val in record.__dict__.items():  # call-site extras
            if key not in _RESERVED and not key.startswith("_"):
                data[key] = val
        if record.exc_info and record.exc_info[0] is not None:
            data["error.type"] = record.exc_info[0].__name__
            if self.log_stacks:
                data["error.stack"] = self.formatException(record.exc_info)
        return json.dumps(redact(data), default=str, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Human-friendly dev formatter (LOG_FORMAT=console)."""

    def format(self, record: logging.LogRecord) -> str:
        ctx = current_context()
        rid = ctx.get("request_id", "-")
        return f"{record.levelname:<8} {record.name} [{rid}] {record.getMessage()}"


def build_formatter(settings: Settings) -> logging.Formatter:
    if settings.log_format == "console":
        return ConsoleFormatter()
    return JsonLogFormatter(
        service=settings.service_name, env=settings.env_name, log_stacks=settings.log_stacks
    )


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once, idempotently: a single stdout JSON handler."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(build_formatter(settings))
    root.addHandler(handler)
    access = logging.getLogger("uvicorn.access")  # prints the raw request path, token included
    if not any(isinstance(f, SecretPathFilter) for f in access.filters):
        access.addFilter(SecretPathFilter())
