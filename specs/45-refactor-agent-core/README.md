# Spec 45 — Refactor: Agent Core

**Type:** 🔧 refactor  ·  **Phase:** AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. This is a
**refactoring spec**: it adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). Follow its method exactly.
2. **Confirm prerequisites.** Depends on: **41, 42, 43, 44** (the entire agent
   core — graph/foundation, tools, diff generation, API/streaming). All must be
   implemented and their tests green before you start.
3. **Study the Overleaf reference (for understanding only).** **There is none.**
   Overleaf has no AI agent — nothing to study or copy. This refactor concerns
   only Inkstave's own agent code.
4. **Scan, evaluate, fix.** Systematically review the agent core for bugs,
   prompt-injection risks, unbounded loops / token-cost blow-ups, DI leaks
   (e.g. `openai` imported outside the client wrapper), missing/weak tests, and
   dead code. For **each** finding, judge risk vs. value and apply only the
   worthwhile fixes. Keep the suite **green** at every step.
5. **Keep behavior stable.** No new capabilities, no new endpoints, no schema
   changes unless required to fix a real defect (and then ship an Alembic
   migration). Public contracts from 41–44 stay intact unless a fix demands a
   documented change.
6. **Verify.** Full suite passes and stays under the 2-minute budget. The LLM is
   still always mocked (`FakeLLM`).
7. **Record what changed and what you deliberately skipped** in a changelog under
   `docs/` (see spec.md §5).

When all Definition-of-Done items pass, this spec is complete. Move to spec 46.

## One-line goal

The agent core (graph, tools, diff generation, API/streaming) is **hardened and
cleaned up** — known bugs fixed, prompt-injection and runaway-cost risks reduced,
DI boundaries enforced, test gaps closed — with all behavior preserved and the
suite green.

## Do NOT (scope guard)

- Do not add new features, endpoints, tools, or UI (those are specs 46–49).
- Do not rewrite working subsystems wholesale; prefer minimal, well-tested fixes.
- Do not introduce real LLM calls into the test suite.
- Do not copy Overleaf source code (there is none for the agent).
