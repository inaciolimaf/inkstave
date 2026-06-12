# Spec 94 — Fix-Pack: Injectable Clock for Auth Time Logic

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it introduces a small, focused infrastructure seam (an injectable
`Clock`) and threads it through the **security-critical auth/token time paths**
so they become deterministically testable. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Respect the prerequisite order.** This pack edits
   `backend/src/inkstave/services/account.py` (also touched by spec 93) and the
   auth token files (`auth/tokens.py`, `auth/refresh_store.py`, also touched by
   specs 92 and 93). It **must be applied AFTER specs 92 and 93** so it builds on
   their final form of those files. Do not apply it before them.
3. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit. Make the **smallest change** that resolves each issue. Do not reformat
   untouched lines, restructure modules, or "improve" unrelated code.
4. **Keep default behaviour identical.** Every production call site must compile
   and behave exactly as before when no clock is supplied. The clock parameter
   defaults to the system clock; this pack changes *testability*, not runtime
   behaviour.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2, ARQ, pytest). Match the existing
   style and test patterns. There is **no Overleaf equivalent** for this seam.
6. **Test.** After applying the fixes, run the backend test suite. It must be
   **green** and the full suite must stay **under 2 minutes**. Add the new unit
   tests described in §8 (Test plan). Use `just test-timed` (xdist) to confirm
   the budget. The new tests must use a `FrozenClock` — **no real sleeps**.

When every issue in `spec.md` is resolved, its acceptance criteria pass, and the
suite is green and under budget, this fix-pack is complete.

## One-line goal

Introduce a small injectable `Clock` abstraction so security-critical time logic
(token expiry, refresh rotation, email-change expiry) is deterministically
testable, replacing scattered direct `datetime.now(UTC)` calls in the auth paths.

## Do NOT (scope guard)

- Do not edit files outside §2 of `spec.md`.
- Do not apply this pack before specs 92 and 93 (ordering prerequisite).
- Do not sweep every `datetime.now(UTC)` site in the codebase — only the auth
  seams listed in §3. The other sites are an explicit, documented follow-up (§4).
- Do not change default runtime behaviour; the clock defaults to system time.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not copy Overleaf source code (there is no Overleaf equivalent here).
- Do not let the suite exceed the 2-minute budget; use `FrozenClock`, never sleeps.
