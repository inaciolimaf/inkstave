# Spec 54 — End-to-End Suite

**Type:** 🟢 feature  ·  **Phase:** Hardening, packaging & docs  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **09** (frontend foundation,
   auth pages, API client), **16–19** (project dashboard, file-tree UI, editor,
   autosave), **24** (PDF preview UI), **31–33** (Yjs binding, presence,
   collaborators & sharing), **46–47** (agent chat UI, diff-review/apply UI). All
   must be implemented and green. It must fit the **spec 53** budget gate.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn how they organize acceptance/e2e suites, then write
   your own Playwright specs.
4. **Implement** the Playwright suite, the test environment bring-up (compose/test
   profile), and the stubs (LLM, fast Tectonic path) in `spec.md`.
5. **Write the tests** — this spec *is* the tests; plus a tiny harness/fixtures.
6. **Verify.** Run the full suite; e2e must fit inside the 2-minute total budget
   (smoke tier). Check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add an e2e-strategy note (smoke vs full, bring-up) under
   `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 55.

## One-line goal

A Playwright end-to-end suite exercises the core user journeys — register/login →
project → files → edit → compile → preview → share & two-user live collab →
version history → AI agent proposes a diff and the user applies it — fast enough
to live inside the 2-minute budget.

## Do NOT (scope guard)

- Do not run a real LLM or a heavy real LaTeX compile in the default e2e tier;
  stub the LLM and use a mocked/precompiled/tiny Tectonic path.
- Do not re-test unit-level logic through the browser; e2e covers user-visible
  journeys only.
- Do not copy Overleaf source code (their Cypress/acceptance specs are reference
  for *organization* only).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`): use
  Playwright and the existing compose/test profile.
