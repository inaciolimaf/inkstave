# Spec 39 — Notifications & Email (async via ARQ)

**Type:** 🟢 feature  ·  **Phase:** Phase 5 — Version history  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on **33** (collaborators &
   sharing: invites and roles) and **04** (testing foundation: fixtures, ARQ test
   harness, the 2-minute budget). They must already be implemented and passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach, then write your own implementation.
4. **Implement** a pluggable email sender (SMTP default; console/file sender in
   dev & tests), email dispatch via ARQ jobs (invite emails; password-reset
   groundwork), an in-app notifications table + endpoints (list / mark-read /
   dismiss), invite surfacing, and a frontend notifications bell (shadcn).
5. **Write the tests** listed in the spec's Test plan (unit / integration / a
   small frontend test). All email sending is via ARQ jobs and is **mocked** in
   tests — no real SMTP.
6. **Verify.** Run the full test suite. It must pass and stay under the 2-minute
   budget. Then check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. sender
   abstraction, notification TTL), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 40.

## One-line goal

Invites and other events produce in-app notifications and async-dispatched emails
(SMTP in prod, console/file in dev/tests), surfaced via a notifications bell — all
without blocking HTTP requests.

## Do NOT (scope guard)

- Do not send email synchronously inside a request handler — always enqueue an ARQ job.
- Do not implement marketing/newsletter email.
- Do not build the full password-reset flow — only the **groundwork** (a reusable
  templated email job + token-less plumbing); the full flow is a later/settings spec.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
