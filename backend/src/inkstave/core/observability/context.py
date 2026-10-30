"""Per-request/job correlation context via contextvars (spec 51 §5.2.2).

Any log call anywhere in a request, WebSocket session, or ARQ job automatically
picks up these fields through the logging filter — no manual threading of ids.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
project_id_var: ContextVar[str | None] = ContextVar("project_id", default=None)
ws_session_id_var: ContextVar[str | None] = ContextVar("ws_session_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
job_name_var: ContextVar[str | None] = ContextVar("job_name", default=None)

_VARS: dict[str, ContextVar[str | None]] = {
    "request_id": request_id_var,
    "trace_id": trace_id_var,
    "user_id": user_id_var,
    "project_id": project_id_var,
    "ws_session_id": ws_session_id_var,
    "job_id": job_id_var,
    "job_name": job_name_var,
}


def bind_context(**fields: str | None) -> dict[str, Token[str | None]]:
    """Set the provided context vars; return reset tokens keyed by field name."""
    tokens: dict[str, Token[str | None]] = {}
    for name, value in fields.items():
        var = _VARS.get(name)
        if var is not None:
            tokens[name] = var.set(value)
    return tokens


def clear_context(tokens: dict[str, Token[str | None]]) -> None:
    """Reset each var to the value it held before its matching ``bind_context``."""
    for name, token in tokens.items():
        var = _VARS.get(name)
        if var is not None:
            var.reset(token)


def reset_all() -> None:
    """Hard-reset every context var to None (used at job/WS boundaries)."""
    for var in _VARS.values():
        var.set(None)


def current_context() -> dict[str, str]:
    """The currently-bound (non-None) context fields, for the log formatter."""
    out: dict[str, str] = {}
    for name, var in _VARS.items():
        value = var.get()
        if value is not None:
            out[name] = value
    return out
