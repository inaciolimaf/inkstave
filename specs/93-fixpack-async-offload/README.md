# Spec 93 — Fix-Pack: Async Offload of CPU-Bound & Blocking Calls

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it bundles a set of **confirmed issues** where CPU-bound or blocking
work runs inline on the asyncio event loop. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Apply AFTER spec 92.** This pack edits `services/auth.py` and
   `services/user.py`, which **spec 92 also edits**. Per the numerical-order rule
   in `CLAUDE.md`, specs are implemented sequentially: confirm **spec 92 is fully
   implemented and green before you start spec 93**, then apply your changes on top
   of spec 92's versions of those files to avoid churn/conflicts.
3. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. Make the smallest change that resolves each issue. **Do not touch any
   file outside the listed set.** If a fix seems to need a file that is not in
   scope, stop and report rather than reaching outside the set.
4. **Do not refactor unrelated code.** Wrap the named blocking call in a thread
   offload and nothing more. Do not reformat untouched lines or restructure modules.
5. **Keep the stack fixed.** **Do not add new dependencies** (no `aiofiles`,
   no thread-pool libraries). Use the stdlib `asyncio.to_thread(...)` only. The
   stack is fixed per `CLAUDE.md` (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ,
   pytest). Match the existing style and test patterns.
6. **Preserve behaviour exactly.** Every offloaded call must produce **byte-for-byte
   identical** results and identical control flow (including the Argon2 timing-attack
   mitigation in the login path and the best-effort blob cleanup in the upload path).
7. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the focused
   tests described in §5 (Test plan). Use `just test-timed` (xdist) to confirm the
   budget.

When every issue in `spec.md` is resolved, its acceptance criterion passes, and
the suite is green and under budget, this fix-pack is complete.

## One-line goal

Stop CPU-bound hashing (Argon2, SHA-256) and blocking file I/O from stalling the
single asyncio event loop under load by offloading those calls to a worker thread
via `asyncio.to_thread`, with identical behaviour.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not add new dependencies (no `aiofiles`); use stdlib `asyncio.to_thread` only.
- Do not change hashing parameters, output formats, or control flow.
- Do not start before spec 92 is implemented and green (shared files).
- Do not copy Overleaf source code (no Overleaf equivalent exists for this pack).
- Do not let the suite exceed the 2-minute budget.
