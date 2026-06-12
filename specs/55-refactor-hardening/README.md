# Spec 55 — Refactor: hardening

**Type:** 🔧 refactor  ·  **Phase:** Hardening, packaging & docs  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. This is a
**refactoring spec** (every 5th): it adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md) next to this file. Follow its scan → evaluate → apply →
   keep-green → changelog process exactly.
2. **Confirm prerequisites.** This spec depends on **51, 52, 53, 54** (the whole
   hardening phase: observability, security hardening, performance & test speed,
   the e2e suite) being implemented with passing tests.
3. **Study the Overleaf reference:** none for this spec. Refactoring is driven by
   Inkstave's own code, the earlier specs' acceptance criteria, and the rules in
   `CLAUDE.md`. (You still must not introduce Overleaf code.)
4. **Scan** the hardening surface — logging/metrics/tracing, rate
   limiting/validation/headers/CORS/uploads/secrets, test-speed harness & budget
   gate, and the Playwright e2e suite — for bugs, **flaky tests**, **slow tests
   breaching the budget**, **security misses**, observability gaps and smells.
   **Evaluate** each finding (risk vs. value). **Apply** only the worthwhile
   fixes. Record what you changed and what you deliberately skipped.
5. **Keep everything green** and within the 2-minute test budget. Add tests that
   close real gaps you found.
6. **Verify** against the Definition of Done.

When all Definition-of-Done items pass, this spec is complete. Move to spec 56.

## One-line goal

The Phase-7 hardening surface (observability, security, performance/test-speed,
e2e) is measurably more correct, secure, fast and de-flaked — with no new
features, no regressions, and a recorded changelog of what was fixed and what was
intentionally left.

## Do NOT (scope guard)

- Do not add new features or new surfaces. Bug fixes, hardening, de-flaking,
  test-speed and clarity refactors only.
- Do not change the approved stack, the metric/log field contracts, or the rate-
  limit policy semantics unless fixing a real defect (note it in the changelog).
- Do not copy Overleaf source code.
- Do not make changes that drop test coverage or push the suite over 2 minutes —
  this pass actively *defends* the budget.
- Do not silently change behaviour the earlier specs' acceptance criteria
  guarantee; if a criterion was wrong, fix it and note it explicitly.
