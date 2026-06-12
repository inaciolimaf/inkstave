# Spec 08 — Auth Guards & Sessions

**Type:** 🟢 feature  ·  **Phase:** Auth & users  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **06** (User model) and
   **07** (token service, refresh store, login/refresh/logout). They must be
   implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md`. **Do not copy or translate any
   Overleaf code.** Learn how its middleware gates routes and admin actions, then
   write your own FastAPI dependencies.
4. **Implement** the FastAPI auth dependencies (`get_current_user`,
   `require_admin`, optional-auth), the protected-route conventions, the
   401/403 semantics, refresh-token reuse/revocation enforcement on protected
   flows, rate-limiting groundwork on auth endpoints, and a sample
   protected endpoint (`GET /api/v1/users/me`) to prove the guards. Also write
   the **WebSocket auth contract** documentation (no live WS — that's spec 29).
5. **Write the tests** listed in the spec's Test plan (unit + integration).
6. **Verify.** Run the full suite (< 2 minutes); check every Acceptance criterion
   and Definition-of-Done item.
7. **Record decisions.** Add/extend an ADR under `docs/` for the WS-auth contract
   and the rate-limiting approach.

When all Definition-of-Done items pass, this spec is complete. Move to spec 09.

## One-line goal

Backend routes can declare "logged-in only", "admin only" or "optional auth"
with a one-line FastAPI dependency, returning correct 401/403 semantics, and the
contract for authenticating future WebSocket connections is documented.

## Do NOT (scope guard)

- Do not build the real WebSocket server or collaboration — only **document** the
  JWT-over-WS contract (built in spec 29).
- Do not build a full production rate limiter — only the **groundwork**
  (pluggable dependency + a working basic limiter on auth endpoints); full
  hardening is spec 52.
- Do not build the frontend (spec 09) or project/file features (Phase 2).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
