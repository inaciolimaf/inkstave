# Spec 59 — User Settings & Profile

**Type:** 🟢 feature  ·  **Phase:** Phase 7 — Hardening, packaging & docs  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **06** (User model,
   registration, argon2 hashing) and **09** (frontend foundation: Vite/React/TS/
   Tailwind/shadcn, routing, API client, auth pages). It also relies on **07/08**
   (JWT auth, current-user dependency, protected routes) and the CodeMirror
   editor (**18**) for applying editor preferences. They must already be
   implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the *shape* of the account/settings flows, then
   write your own.
4. **Implement** the backend (profile update, change email with confirmation
   groundwork, change password, editor preferences persistence, account
   deletion) and the frontend settings pages (shadcn), applying editor
   preferences to CodeMirror.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
6. **Verify.** Run the full suite; it must pass and stay under 2 minutes. Then
   check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. how editor
   preferences are stored/applied, the email-change confirmation model), add a
   short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 60.

## One-line goal

A signed-in user can manage their account — edit profile (display name, optional
avatar), change email (with confirmation groundwork), change password, set editor
preferences (theme, font size, keymap) that persist and apply to CodeMirror, and
delete their account — via backend endpoints and shadcn settings pages.

## Do NOT (scope guard)

- Do not build admin user-management, billing, or team features.
- Do not implement a full transactional email delivery system — only the
  email-change **confirmation groundwork** (token generation/verification + an
  ARQ send-hook that may reuse spec 39's notification/email plumbing if present;
  otherwise stub the send). No SMTP provider setup here.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
