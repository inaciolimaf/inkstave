# Spec 07 — JWT Authentication

**Type:** 🟢 feature  ·  **Phase:** Auth & users  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **06** (the `User` model and
   `verify_password`). It also relies on the Redis client/connection established
   in earlier foundation specs (02/03) — if no shared Redis dependency exists
   yet, add a minimal async Redis provider here.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code.** Note:
   **Overleaf authenticates with server sessions + Passport, not JWT.** Inkstave's
   JWT design is its *own*; use Overleaf only to understand the **login flow**
   (find user by email → constant-time password check → uniform failure on bad
   email or bad password). Do not try to mirror its session model.
4. **Implement** the token service (sign/verify access + refresh), the
   server-side refresh-token store (Redis) with rotation and reuse detection, and
   the `login` / `refresh` / `logout` endpoints described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit + integration).
6. **Verify.** Run the full test suite (< 2 minutes) and check every Acceptance
   criterion and Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` covering the token model
   (HS256, lifetimes, rotation, reuse detection, secret rotation strategy).

When all Definition-of-Done items pass, this spec is complete. Move to spec 08.

## One-line goal

A registered user can log in to receive a short-lived access token and a
long-lived rotating refresh token, refresh the pair, and log out to revoke it.

## Do NOT (scope guard)

- Do not implement the `get_current_user` / `require_admin` FastAPI dependencies
  or apply guards to other routes — that is spec **08**.
- Do not implement WebSocket auth (documented as a contract in 08, built in 29).
- Do not implement rate limiting (groundwork in 08).
- Do not build any frontend (spec 09).
- Do not copy Overleaf source code or replicate its session/Passport model.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
