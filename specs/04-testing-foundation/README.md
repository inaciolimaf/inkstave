# Spec 04 — Testing Foundation

**Type:** 🟢 feature  ·  **Phase:** Phase 0 — Foundations  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **02** (app factory,
   settings, Redis provider, error envelope) and **03** (async engine/session,
   `Base`, Alembic, `pings` table). Both must be implemented and passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — AGPLv3 vs
   MIT. Learn how the test suites are *organized and tiered*, then write your own.
4. **Implement** the layered test infrastructure: pytest + pytest-asyncio +
   `httpx.AsyncClient`; a fast ephemeral test-Postgres strategy (template DB +
   transactional rollback per test); a Redis fake; factory helpers; coverage;
   Vitest + React Testing Library scaffolding; Playwright scaffolding with the
   app stubbed; and a GitHub Actions CI workflow running every tier — all as
   described in `spec.md`, with an explicit **< 2-minute** budget strategy.
5. **Write the tests** that prove the harness itself works (a couple of sample
   tests per tier). Feature tests come with their own specs.
6. **Verify.** Run the full test suite. It must pass and stay under the 2-minute
   budget. Then check every Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add an ADR under `docs/` documenting the test-DB
   strategy and the budget-keeping rules every later spec must follow.

When all Definition-of-Done items pass, this spec is complete. Move to spec 05.

## One-line goal

After this spec Inkstave has fast, layered, CI-wired test infrastructure
(pytest/Vitest/Playwright) with reusable fixtures and factories, a sub-2-minute
budget strategy (template DB, fakes, no real LaTeX/LLM), so every later spec can
add tests by convention.

## Do NOT (scope guard)

- Do not write feature tests for features that do not exist yet — only sample
  tests that exercise the harness.
- Do not introduce real LaTeX (Tectonic) or real LLM calls into any test tier —
  those are always mocked/stubbed.
- Do not build the production Docker images or deploy CI (spec 56/57). Only the
  test-running CI workflow is in scope.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
