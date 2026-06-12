# Spec 06 — User Model & Registration

**Type:** 🟢 feature  ·  **Phase:** Auth & users  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **03** (database foundation:
   async SQLAlchemy, Alembic, base model/timestamp mixins, test DB) and **04**
   (testing foundation: pytest fixtures, httpx app client, 2-minute budget). They
   must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
   Note: Overleaf hashes passwords with **bcrypt**; Inkstave uses **argon2** —
   study Overleaf only for the *shape* of the flow (validate → check duplicate →
   hash → persist), not the algorithm.
4. **Implement** the backend changes described in `spec.md`: the `User` model,
   the argon2 password-hashing service, the registration endpoint, Pydantic
   schemas, and the Alembic migration (including the `citext` extension).
5. **Write the tests** listed in the spec's Test plan (unit + integration). No
   e2e in this spec.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. argon2
   parameters, citext vs. lower() unique index), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 07.

## One-line goal

A person can create an Inkstave account by POSTing an email, password and
display name, and the account is persisted with an argon2-hashed password.

## Do NOT (scope guard)

- Do not implement login, token issuance, sessions, or any auth guards — that is
  spec **07** and **08**.
- Do not implement email confirmation flows, password reset, or the frontend —
  later specs. (This spec only adds the `email_confirmed` *column*, defaulting to
  `false`; it does not send or verify anything.)
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
