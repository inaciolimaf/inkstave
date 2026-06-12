# Spec 103 — Email delivery (Mailpit dev inbox + Resend production)

**Type:** 🟢 feature  ·  **Phase:** Hardening / operability  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. This spec **builds on the existing mailer**
   (`backend/src/inkstave/mailer/`): the `EmailSender` Protocol,
   `ConsoleEmailSender`/`FileEmailSender`/`SmtpEmailSender`, `get_email_sender`,
   the `send_email_job` ARQ job, `EmailEnqueuer`, and `render_email`. **Do not
   duplicate or rewrite** any of that — extend it. If something is ambiguous,
   prefer the simplest option consistent with `CLAUDE.md` and stop to ask rather
   than invent scope.
2. **Confirm prerequisites.** This spec depends on: **39** (mailer pipeline:
   senders, ARQ send job, enqueuer, templates), **06–08** (user model, JWT auth,
   guards/sessions), **59** (user settings: email-change confirmation +
   `email_change_token_ttl`), **33** (sharing invites, which already enqueue the
   `project_invite` email). They must already be implemented and their tests
   passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** the backend + infra + docs changes described in `spec.md`:
   the optional `ResendEmailSender`, the `get_email_sender` `resend` branch, the
   Mailpit dev compose service + dev email config, the `RESEND_API_KEY` /
   `EMAIL_BACKEND=resend` config, the missing transactional triggers
   (account email verification + password reset) and their templates, the
   `send-test-email` CLI subcommand, the `just mail` recipe, and the admin-guide
   docs (Mailpit, Resend SMTP + native, SPF/DKIM/domain verification).
5. **Write the tests** listed in the spec's Test plan (unit / integration). No
   test may depend on a running Mailpit, a real SMTP server, or a real Resend
   account/key.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. the native
   Resend sender vs. SMTP-only), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete.

## One-line goal

A developer sees every outgoing email in a local Mailpit inbox at
`http://localhost:8025`, and production can deliver real mail through Resend
(via the existing SMTP sender or an optional native HTTP-API sender) with no
secrets hard-coded and no request ever blocked on sending.

## Do NOT (scope guard)

- Do not implement features that belong to later specs (see `specs/README.md`).
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not rewrite the existing mailer (spec 39); extend it through the Protocol /
  `get_email_sender` DI boundary so tests keep swapping a fake.
- Do not make any automated test depend on Mailpit, a real SMTP server, or a
  real Resend key/account.
