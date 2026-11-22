"""Request-id accessors over the shared observability context var.

The id is bound by :class:`~inkstave.core.observability.middleware.RequestContextMiddleware`;
logging itself is configured in :mod:`inkstave.core.observability.log`.
"""

from __future__ import annotations

from inkstave.core.observability.context import request_id_var as request_id_ctx


def get_request_id() -> str | None:
    """Return the current request's correlation id, if any."""
    return request_id_ctx.get()


def set_request_id(request_id: str | None) -> None:
    """Bind ``request_id`` to the current context."""
    request_id_ctx.set(request_id)
