# Spec 105 — Sandboxed Compiles for Public Multi-Tenant Operation

**Type:** 🔒 hardening · **Phase:** security / isolation · **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one hardening spec** of the Inkstave system. Its goal is
to make Inkstave safe to run for a **public, mutually-untrusted** user base by
isolating every LaTeX compile in its own ephemeral, gVisor-sandboxed container.
Do this:

1. **Read the requirements.** The authoritative, per-item detail is in
   [`spec.md`](spec.md) next to this file. Apply *every* item there — no more, no
   less. The "Threat model" section records what is covered and what residual
   risk is deliberately accepted.
2. **Inspect the real code first.** Confirm the seams named in `spec.md`
   (`compile/runner.py`, `compile/limits.py`, `compile/worker.py`,
   `security/rate_limit.py`, `compile/coordinator.py`, `config_groups.py`) still
   match before editing. Make the **smallest change** that resolves each item.
3. **Add, never alter.** The sandbox is a *new* injectable `TectonicRunner`
   implementation. **Do not change** `LocalTectonicRunner`, `CompileService`, or
   `compile/jobs.py` — the runner is selected by env (`COMPILE_RUNNER`) and
   wired in the worker bootstrap only.
4. **Anti-injection is a hard rule.** No user-controlled data (filenames, file
   contents) may ever enter the `docker` argv. The argv is a fixed list executed
   with `create_subprocess_exec` (no shell). User filenames live only inside the
   read-only mount and are validated before use.
5. **Follow `CLAUDE.md`.** No Overleaf code copied; the stack is fixed
   (FastAPI, SQLAlchemy 2.x async, Pydantic v2 settings, pytest). Match the
   existing style, the `config_groups.py` settings pattern, and the
   `security/rate_limit.py` named-policy pattern.
6. **Tests stay fast and offline.** A real container **never** runs in CI. Unit
   tests assert the *constructed argv* (the non-executing seam) and the
   validation/quota/egress guards. Keep the full suite **green and under 2
   minutes** (`just test-timed`).

When every item in `spec.md` is resolved, its acceptance criteria pass, the docs
and README carry no contradictory "trusted-users only" text, and the suite is
green and under budget, this spec is complete.

## One-line goal

Run each LaTeX compile in a throwaway gVisor (`runsc`) container with no network,
dropped capabilities, and hard resource caps — so a malicious document can harm
nothing but its own sandbox — and gate abuse with a daily compile quota.

## No Overleaf equivalent

Overleaf Community Edition has **no per-user compile isolation**; its commercial
Server Pro does, but that is closed source. There is **nothing to study in
`../overleaf/`** for this spec — the sandbox runner, the offline compile image,
the hardened docker-daemon access, and the daily quota are all
Inkstave-internal. Do **not** look for or copy an Overleaf approach.

## Do NOT (scope guard)

- Do not edit `LocalTectonicRunner`, `CompileService`, or `compile/jobs.py`.
- Do not let any user-controlled string reach the `docker` argv.
- Do not put `docker.sock` on the public API service — only the compile worker.
- Do not run a real container in any test tier.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not let the suite exceed the 2-minute budget.
