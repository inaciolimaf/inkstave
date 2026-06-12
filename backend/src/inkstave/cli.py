"""Inkstave operations CLI (spec 57).

    python -m inkstave.cli migrate          # advisory-locked alembic upgrade head
    python -m inkstave.cli bootstrap-admin  # create the first admin (idempotent)
    python -m inkstave.cli seed --demo       # demo user + project (never in prod)
    python -m inkstave.cli check-config      # validate env/secrets; exit non-zero on error
    python -m inkstave.cli doctor            # config + Postgres/Redis reachability (spec 62)

Stdlib argparse only — no extra dependency. Each command returns a process exit
code so it doubles as a deploy/CI gate.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING

from inkstave.auth.password import build_password_hasher
from inkstave.bootstrap.admin import ensure_initial_admin
from inkstave.bootstrap.config_check import format_config_problems, validate_config
from inkstave.bootstrap.migrate import run_upgrade
from inkstave.bootstrap.seed import seed_demo
from inkstave.config import get_settings
from inkstave.db.engine import create_engine_and_sessionmaker

if TYPE_CHECKING:
    from inkstave.config import Settings

# A dependency probe returns True when the service is reachable. Injectable so the
# fast test tier passes fakes and never touches a real Postgres/Redis.
DepCheck = Callable[[], Awaitable[bool]]


def _cmd_migrate() -> int:
    run_upgrade(get_settings())
    print("migrations applied (at head)")
    return 0


def _cmd_check_config() -> int:
    errors = validate_config()
    if errors:
        print("config invalid:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("config ok")
    return 0


async def _default_db_check(settings: Settings) -> bool:
    """Real Postgres probe: ``SELECT 1`` honouring the readiness timeout."""
    from inkstave.db.engine import check_db

    if not settings.database_url:
        return False
    engine, _ = create_engine_and_sessionmaker(settings)
    try:
        return await check_db(engine, settings.readiness_check_timeout_s)
    finally:
        await engine.dispose()


async def _default_redis_check(settings: Settings) -> bool:
    """Real Redis probe: ``PING`` honouring the readiness timeout."""
    from inkstave.redis_client import create_redis_pool, ping_redis

    redis = await create_redis_pool(settings.redis_url)
    try:
        return await ping_redis(redis, settings.readiness_check_timeout_s)
    finally:
        await redis.aclose()


async def _probe(check: DepCheck, label: str, name: str) -> bool:
    """Run a probe, printing one friendly PASS/FAIL line (never a traceback)."""
    try:
        ok = await check()
    except Exception as exc:  # noqa: BLE001 — reachability diagnostics never raise out
        print(f"{name}: FAIL ({label}) — {type(exc).__name__}: {exc}", file=sys.stderr)
        return False
    if ok:
        print(f"{name}: PASS ({label})")
    else:
        print(f"{name}: FAIL ({label}) — not reachable", file=sys.stderr)
    return ok


async def _cmd_doctor(
    *,
    config_check: Callable[[], list[str]] | None = None,
    db_check: DepCheck | None = None,
    redis_check: DepCheck | None = None,
) -> int:
    """Report config validity + Postgres/Redis reachability; exit 0 only if all pass.

    The probes are injectable (``db_check``/``redis_check``) so tests pass fakes;
    by default they build the real readiness probes from the current settings.
    """
    problems = (config_check or validate_config)()
    if problems:
        print("config: FAIL", file=sys.stderr)
        print(format_config_problems(problems), file=sys.stderr)
    else:
        print("config: PASS")

    # Build settings for the default probes (only if a real probe will run).
    settings: Settings | None = None
    if db_check is None or redis_check is None:
        try:
            settings = get_settings()
        except Exception:  # noqa: BLE001 — config already reported above
            settings = None

    db_label = (settings.database_url if settings else None) or "<unset>"
    redis_label = settings.redis_url if settings else "<unset>"

    if db_check is None:
        db_check = (lambda: _default_db_check(settings)) if settings else _unreachable
    if redis_check is None:
        redis_check = (lambda: _default_redis_check(settings)) if settings else _unreachable

    db_ok = await _probe(db_check, db_label, "postgres")
    redis_ok = await _probe(redis_check, redis_label, "redis")

    return 0 if (not problems and db_ok and redis_ok) else 1


async def _unreachable() -> bool:
    """Probe used when settings could not be built — nothing to connect to."""
    return False


def _resolve_admin_credentials() -> tuple[str, str] | None:
    """Read the admin email/password from env, prompting on a TTY (sync — no loop)."""
    email = os.environ.get("INKSTAVE_ADMIN_EMAIL")
    password = os.environ.get("INKSTAVE_ADMIN_PASSWORD")
    if not email and sys.stdin.isatty():
        email = input("Admin email: ").strip()
    if not password and sys.stdin.isatty():
        password = getpass.getpass("Admin password: ")
    if not email or not password:
        print(
            "set INKSTAVE_ADMIN_EMAIL and INKSTAVE_ADMIN_PASSWORD (or run on a TTY)",
            file=sys.stderr,
        )
        return None
    return email, password


async def _cmd_bootstrap_admin(email: str, password: str) -> int:
    settings = get_settings()
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    hasher = build_password_hasher(settings)
    try:
        async with sessionmaker() as session:
            admin = await ensure_initial_admin(
                session,
                hasher,
                email=email,
                password=password,
                display_name=email.split("@", 1)[0],
            )
            await session.commit()
        print(f"admin created: {admin.email}" if admin else "admin already exists")
        return 0
    finally:
        await engine.dispose()


async def _cmd_seed(*, demo: bool, force: bool) -> int:
    if not demo:
        print("nothing to seed (pass --demo)", file=sys.stderr)
        return 2
    settings = get_settings()
    engine, sessionmaker = create_engine_and_sessionmaker(settings)
    hasher = build_password_hasher(settings)
    try:
        async with sessionmaker() as session:
            try:
                created = await seed_demo(session, hasher, settings=settings, force=force)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            await session.commit()
        print("demo seeded" if created else "demo already present")
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inkstave", description="Inkstave operations CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply Alembic migrations to head (advisory-locked)")
    sub.add_parser("bootstrap-admin", help="create the first admin (idempotent)")
    seed_parser = sub.add_parser("seed", help="optional demo data")
    seed_parser.add_argument("--demo", action="store_true", help="seed a demo user + project")
    seed_parser.add_argument("--force", action="store_true", help="allow seeding in production")
    sub.add_parser("check-config", help="validate env/secrets; non-zero exit on error")
    sub.add_parser("doctor", help="config + Postgres/Redis reachability; non-zero on any failure")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _cmd_migrate()
    if args.command == "check-config":
        return _cmd_check_config()
    if args.command == "doctor":
        return asyncio.run(_cmd_doctor())
    if args.command == "bootstrap-admin":
        creds = _resolve_admin_credentials()
        if creds is None:
            return 2
        return asyncio.run(_cmd_bootstrap_admin(*creds))
    if args.command == "seed":
        return asyncio.run(_cmd_seed(demo=args.demo, force=args.force))
    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":
    raise SystemExit(main())
