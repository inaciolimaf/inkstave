# Spec 91 — Fix-Pack: Secret Hygiene (exposed key + commit guard)

**Type:** 🔧 fix-pack  ·  **Phase:** hardening / cleanup  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec: it closes a single **secret-hygiene finding** from a code-smell
audit. Do this:

1. **Read the requirements.** The authoritative, per-issue detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* issue listed there —
   no more, no less.
2. **Stay in scope.** The files in §2 of `spec.md` are the **only** files you may
   edit (plus a single new ADR under `docs/`). **Do not touch any file outside
   the listed set.** If a fix seems to need a file that is not in scope, stop and
   report rather than reaching outside the set.
3. **Never write, print, paste, or echo a real secret.** The audit found a real
   OpenRouter key in the developer's local `.env` (which is gitignored and was
   never committed). You must **not** read its value into any committed file, log,
   commit message, test fixture, or this spec's output. The only secret-shaped
   strings allowed anywhere in the repo are obvious dummies/placeholders. Treat
   this as a hard rule that overrides convenience.
4. **Do not refactor unrelated code.** Make the smallest change that resolves
   each issue. Do not reformat untouched lines.
5. **Follow `CLAUDE.md`.** The stack is fixed; this pack is config + docs only.
   Match the existing style of `.pre-commit-config.yaml`, `.gitignore`, and the
   `docs/` ADRs.
6. **Verify.** This pack adds no Python tests. Confirm via
   `pre-commit run --all-files` on the clean tree (must pass) and a manual
   hook-trigger check (a throwaway staged file containing a dummy secret pattern
   must be rejected). The full test suite stays well **under 2 minutes** — no new
   runtime tests are added.

When every issue in `spec.md` is resolved and its acceptance criterion passes,
this fix-pack is complete. Move to the next spec.

## One-line goal

Prevent real secrets from ever being committed and document rotation of the
exposed OpenRouter key — without storing any secret in the repo.

## Do NOT (scope guard)

- Do not write, print, or commit the real OpenRouter key (or any real secret).
- Do not add the real key to `.env.example`; keep only the placeholder.
- Do not edit files outside §2 of `spec.md` (other than the one new ADR in `docs/`).
- Do not weaken the existing `.gitignore` rules for `.env` files.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget (this pack adds no runtime tests).
