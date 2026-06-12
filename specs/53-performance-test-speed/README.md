# Spec 53 — Performance & Test Speed

**Type:** 🟢 feature  ·  **Phase:** Hardening, packaging & docs  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **04** (the testing
   foundation — pytest/Vitest/Playwright setup, fixtures, the existing CI). In
   practice it audits **all prior specs'** tests and hot paths, so the whole
   system must be implemented and green.
3. **Study the Overleaf reference (for understanding only).** None specific to
   this spec — it is general performance/testing engineering. Do not copy any
   Overleaf code.
4. **Implement** the test-speed and runtime-performance changes in `spec.md`,
   and the CI budget gate.
5. **Write/adjust the tests** and the measurement harness in the spec's Test plan.
6. **Verify.** Run the full suite; it must pass **and** the new gate must prove it
   stays under the 2-minute budget. Check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Add a short performance/test-strategy ADR under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 54.

## One-line goal

The full test suite is measured and **hard-gated under 2 minutes** via
parallelization, a fast DB strategy and zero real LaTeX/LLM/network in the fast
tiers, while runtime hot paths are audited for N+1s, indexes, pooling and caching.

## Do NOT (scope guard)

- Do not change product behaviour to make tests faster (no feature regressions);
  speed-ups must be transparent.
- Do not delete meaningful test coverage to hit the budget; reorganize, mock and
  parallelize instead, and justify any removed/quarantined test.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`). Use
  pytest-xdist, Vitest threads, Redis caching (already present), and DB
  transaction/template strategies.
