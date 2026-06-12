# Spec 92 — Fix-Pack: Auth Logging & Exception Visibility (validated issues)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a small set of **confirmed issues** about the
authentication subsystem being effectively unobservable — security-relevant
events pass silently and one `except Exception` swallows its error with no log.
Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. **Do not touch any file outside the listed set.** If a fix seems to need
   a file that is not in scope, stop and report rather than reaching outside it.
3. **Do not refactor unrelated code.** Make the **smallest change** that resolves
   each issue. Do not reformat untouched lines, rename things, or restructure
   modules. This pack adds logging and narrows one exception catch — nothing more.
4. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). **Match the existing
   logging style:** module-level `logger = logging.getLogger(__name__)`, and
   `logger.info/warning(...)` with **%-style args** and/or `extra={...}` (see
   `agent/llm/openrouter.py`, `cache.py`, `exception_handlers.py`).
5. **THE CRITICAL CONSTRAINT — never log secrets.** No log record produced by this
   pack may contain a password, a raw access or refresh token string, or a token
   `jti`/family secret. Log only stable, non-sensitive identifiers (`user_id`) and
   the event name. This is the single most important rule in this spec; a fix that
   leaks a secret into a log is **worse** than the silent behaviour it replaced.
6. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the new/updated
   `caplog`-based tests described in §5 (Test plan), including the assertion that
   the captured log text contains neither the test password nor the raw token.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Make the authentication subsystem observable — log security-relevant events at
appropriate levels and stop swallowing exceptions silently — **without ever
logging a password or a raw token**.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not change any auth control-flow, status codes, close codes, or error
  messages — this pack adds **observability only** (plus one narrowed catch).
- Do not log passwords, raw tokens, jti/family secrets, or full request bodies.
- Do not introduce features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
