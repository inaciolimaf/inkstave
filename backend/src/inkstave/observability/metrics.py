"""Prometheus metric catalogue + thin helpers (spec 51 §5.3). Define-once, reuse-by-name."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from time import perf_counter
from typing import TYPE_CHECKING, Any

from prometheus_client import REGISTRY, Counter, Gauge, Histogram
from prometheus_client import generate_latest as _generate_latest

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("inkstave.observability.metrics")

# Pin the classic Prometheus text exposition content type (spec §5.3 / AC5); newer
# prometheus_client advertises version=1.0.0 but generate_latest stays 0.0.4-compatible.
CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
# Bound the `model` label cardinality (spec §5.3): only known models keep their name.
_MODEL_ALLOWLIST = {"openai/gpt-4o-mini", "openai/gpt-4o", "anthropic/claude-3.5-sonnet"}
_ARQ_QUEUE_KEY = "arq:queue"


def _metric(cls: type, name: str, documentation: str, **kwargs: Any) -> Any:
    """Create the metric, or return the already-registered one (survives module reload)."""
    for collector in list(REGISTRY._collector_to_names.keys()):
        if getattr(collector, "_name", None) == name:
            return collector
    return cls(name, documentation, registry=REGISTRY, **kwargs)


# --- catalogue (counters use base names; prometheus appends _total) ----------- #

http_requests = _metric(
    Counter, "inkstave_http_requests", "HTTP requests", labelnames=("method", "path", "status")
)
http_request_duration = _metric(
    Histogram,
    "inkstave_http_request_duration_seconds",
    "HTTP request duration",
    labelnames=("method", "path"),
    buckets=_DURATION_BUCKETS,
)
ws_connections_active = _metric(
    Gauge, "inkstave_ws_connections_active", "Active WebSocket connections", labelnames=("kind",)
)
ws_messages = _metric(
    Counter, "inkstave_ws_messages", "WebSocket messages", labelnames=("direction", "kind")
)
compile_duration = _metric(
    Histogram,
    "inkstave_compile_duration_seconds",
    "Compile duration",
    labelnames=("engine", "status"),
    buckets=_DURATION_BUCKETS,
)
compile_total = _metric(Counter, "inkstave_compile", "Compiles", labelnames=("status",))
agent_tokens = _metric(
    Counter, "inkstave_agent_tokens", "Agent LLM tokens", labelnames=("direction", "model")
)
agent_requests = _metric(Counter, "inkstave_agent_requests", "Agent runs", labelnames=("status",))
job_queue_depth = _metric(
    Gauge, "inkstave_job_queue_depth", "Pending jobs in a queue", labelnames=("queue",)
)
job_duration = _metric(
    Histogram,
    "inkstave_job_duration_seconds",
    "ARQ job duration",
    labelnames=("job_name", "status"),
    buckets=_DURATION_BUCKETS,
)
build_info = _metric(Gauge, "inkstave_build_info", "Build info", labelnames=("version", "git_sha"))
rate_limit_errors = _metric(
    Counter, "inkstave_rate_limit_errors", "Rate-limit backend failures", labelnames=("policy",)
)


# --- helpers ----------------------------------------------------------------- #


def observe_http(method: str, path: str, status: int, duration_s: float) -> None:
    http_requests.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration.labels(method=method, path=path).observe(duration_s)


def observe_compile(engine: str, status: str, duration_s: float) -> None:
    compile_duration.labels(engine=engine, status=status).observe(duration_s)
    compile_total.labels(status=status).inc()


def inc_agent_tokens(direction: str, model: str, n: int) -> None:
    label = model if model in _MODEL_ALLOWLIST else "other"
    agent_tokens.labels(direction=direction, model=label).inc(n)


def inc_agent_request(status: str) -> None:
    agent_requests.labels(status=status).inc()


def inc_rate_limit_error(policy: str) -> None:
    rate_limit_errors.labels(policy=policy).inc()


def set_build_info(version: str, git_sha: str) -> None:
    build_info.labels(version=version, git_sha=git_sha).set(1)


@contextmanager
def track_ws(kind: str) -> Iterator[None]:
    """Inc the active-connections gauge for the duration; always dec in finally."""
    ws_connections_active.labels(kind=kind).inc()
    try:
        yield
    finally:
        ws_connections_active.labels(kind=kind).dec()


@asynccontextmanager
async def track_job(job_name: str) -> AsyncIterator[None]:
    """Time an ARQ job and label success/error (records inkstave_job_duration_seconds)."""
    start = perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        job_duration.labels(job_name=job_name, status=status).observe(perf_counter() - start)


async def sample_queue_depth(redis: Redis, queue: str = _ARQ_QUEUE_KEY) -> None:
    """Update the queue-depth gauge at scrape time; fail soft if Redis is unreachable."""
    try:
        depth = await redis.zcard(queue)  # type: ignore[misc]
        if not depth:
            depth = await redis.llen(queue)  # type: ignore[misc]
        job_queue_depth.labels(queue=queue).set(float(depth))
    except Exception as exc:  # never 500 /metrics on a Redis hiccup
        logger.warning("queue-depth sample failed: %s", exc)


def render_latest() -> bytes:
    return _generate_latest(REGISTRY)
