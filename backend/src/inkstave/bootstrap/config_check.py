"""Fail-fast config / secret validation (spec 57 §5.6; spec 62 friendly layer).

Re-builds ``Settings`` from the environment so the production guards (JWT strength,
CORS, required ``DATABASE_URL`` — specs 52/57) fire, and adds the runtime checks
the model can't express. Returns a list of human-readable problems; empty = valid.
Wired into ``inkstave.cli check-config``/``doctor`` (exit 0/non-zero) as the
pre-deploy gate; the same production guards also fire at startup because the app
builds ``Settings``.

Spec 62 adds :func:`validate_required_runtime` — a small, pure helper that names
the three always-required vars (``JWT_SECRET``, ``DATABASE_URL``, ``REDIS_URL``)
and reports each missing/malformed one on its own ``"<VAR>: <reason>"`` line, plus
:func:`format_config_problems` to render them without a Python traceback.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from pydantic import ValidationError

from inkstave.config import get_settings

# Accepted DSN prefixes for the well-formedness check (cheap string check only).
_DB_PREFIXES = ("postgresql",)
_REDIS_PREFIXES = ("redis://", "rediss://")


def _scheme(url: str) -> str:
    return url.split("://", 1)[0] if "://" in url else url


def validate_required_runtime(env: Mapping[str, str] | None = None) -> list[str]:
    """Check the always-required runtime vars; return ``"<VAR>: <reason>"`` lines.

    Pure: reads from ``env`` (defaults to :data:`os.environ`) and returns one
    problem line per offending var. Empty list ⇒ all present and well-formed.
    These three vars are required to run the server in **every** environment.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    problems: list[str] = []

    jwt_secret = (source.get("JWT_SECRET") or "").strip()
    if not jwt_secret:
        problems.append("JWT_SECRET: must be set (the server cannot sign tokens without it)")

    database_url = (source.get("DATABASE_URL") or "").strip()
    if not database_url:
        problems.append(
            "DATABASE_URL: must be set (e.g. postgresql+asyncpg://user:pass@host:5432/db)"
        )
    elif not database_url.startswith(_DB_PREFIXES):
        problems.append(
            f"DATABASE_URL: must start with 'postgresql' (got {_scheme(database_url)!r})"
        )

    redis_url = (source.get("REDIS_URL") or "").strip()
    if not redis_url:
        problems.append("REDIS_URL: must be set (e.g. redis://localhost:6379/0)")
    elif not redis_url.startswith(_REDIS_PREFIXES):
        problems.append(
            f"REDIS_URL: must start with 'redis://' or 'rediss://' (got {_scheme(redis_url)!r})"
        )

    return problems


def format_config_problems(problems: list[str]) -> str:
    """Render problems as a one-line summary + one indented line per offender.

    Never contains a Python traceback — this is the developer-facing message.
    """
    summary = f"Configuration error: {len(problems)} problem(s)"
    return "\n".join([summary, *(f"  - {p}" for p in problems)])


def validate_config() -> list[str]:
    """Collect config problems for the current environment (empty list ⇒ valid).

    Combines the friendly required-runtime checks with the production model
    guards. Each problem is one ``"<VAR>: <reason>"`` line; a given var is
    reported at most once (the required-runtime check wins over the raw field
    error so the message stays readable).
    """
    problems = validate_required_runtime()
    reported = {p.split(":", 1)[0] for p in problems}

    get_settings.cache_clear()
    try:
        settings = get_settings()
    except ValidationError as exc:
        for err in exc.errors():
            loc = err.get("loc") or ()
            name = str(loc[0]).upper() if loc else "CONFIG"
            if name in reported:
                continue
            problems.append(f"{name}: {err.get('msg', err)}")
            reported.add(name)
        return problems

    if settings.environment == "prod" and not settings.llm_stub:
        from inkstave.agent.settings import get_agent_settings

        get_agent_settings.cache_clear()
        if not get_agent_settings().openrouter_api_key:
            problems.append(
                "OPENROUTER_API_KEY: required in production for the AI agent "
                "(set LLM_STUB=true only for tests, never production)"
            )

    # Email-backend-gated secrets (spec 103): the selected backend must be usable.
    if settings.email_backend == "resend" and not settings.resend_api_key.strip():
        problems.append("RESEND_API_KEY: required when EMAIL_BACKEND=resend")
    if settings.email_backend == "smtp" and not settings.smtp_host.strip():
        problems.append("SMTP_HOST: required when EMAIL_BACKEND=smtp")
    return problems
