# Spec 104 — Email link-based account flows (verify / magic-link / reset)

**Type:** 🟢 feature  ·  **Phase:** Auth & accounts (post-foundation hardening)  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **06, 07, 08** (User model,
   JWT access+refresh auth, guards/sessions/revocation), **09** (frontend auth
   foundation: `frontend/src/auth/`, login/register pages, `api-client`,
   react-router), **39 + 103** (the async email pipeline + the
   `email_verification` / `password_reset` templates and the
   `POST /api/auth/forgot-password` trigger), **52** (rate limiting), **59** (the
   hashed single-use token pattern in `services/account.py`), **94** (the
   injectable `Clock`). They must already be implemented and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the backend and frontend changes described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add a short ADR under `docs/` noting the
   `auth_tokens` table, the 104↔103 ownership split, and the
   `require-verified-email-to-login` toggle default.

When all Definition-of-Done items pass, this spec is complete. Move to spec NN+1.

## One-line goal

A user can verify their email, sign in passwordlessly, and reset a forgotten
password — each entirely through a single-use, hashed, expiring link they click,
issued and consumed over secure non-enumerating endpoints.

## Ownership split with spec 103 (read before coding)

- **103 owns email DELIVERY:** the `EmailSender` Protocol, Mailpit/Resend
  transport, the `send_email_job` ARQ job, and the `email_verification` /
  `password_reset` template *renderers* already in `mailer/templates.py`. It also
  added the `password_reset_token_ttl` / `email_verification_token_ttl` settings
  and a placeholder `POST /api/auth/forgot-password` route that enqueues a
  `password_reset` email with a **throwaway** `generate_token()` URL.
- **104 owns the FLOWS:** the real token *store* (`auth_tokens` table, hashing,
  single-use, expiry, invalidation), the request **and callback** endpoints for
  all three flows, the non-enumeration semantics, the abuse protection, and the
  frontend pages. 104 **replaces** 103's throwaway tokens with persisted hashed
  tokens and finishes the verification + reset round trips end to end.
- 104 **reuses** 103's two templates as-is and **adds** only one new renderer:
  `magic_login`. Do not duplicate or rewrite 103's delivery code or templates.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not build a typed OTP / numeric-code flow — every flow is a clicked **link**.
- Do not re-implement or fork spec 103's sender, ARQ job, or existing templates.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
