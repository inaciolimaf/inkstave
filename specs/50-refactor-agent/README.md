# Spec 50 — Refactor: Full AI Agent

**Type:** 🔧 refactor  ·  **Phase:** Phase 6 — AI writing agent  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing a **refactoring** spec. It adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). This spec scans the **entire** AI agent feature (specs
   41–49: graph + DI LLM client, tools, diff generation, streaming API, chat UI,
   diff review/apply, context/section parsing, safety & evals) for bugs,
   prompt-injection holes, cost traps, UX issues, and missing tests; evaluates
   each finding (risk vs. value); applies the worthwhile fixes; keeps the suite
   green and under 2 minutes; and records a changelog.
2. **Confirm prerequisites.** Depends on **41–49** — all implemented with passing
   tests.
3. **No Overleaf reference.** This spec has none — Overleaf has no AI agent and
   this spec works only on Inkstave's own code. The originality rule still
   applies: do not copy Overleaf code.
4. **Find → evaluate → apply.** For each candidate fix, judge whether it is worth
   the risk; apply only the worthwhile ones. Skipped findings are recorded with a
   reason. Never weaken the safety invariants (no auto-apply, injection framing,
   budgets/limits, audit) and never auto-apply a diff.
5. **Keep tests green.** Add tests for any bug you fix and any gap you find; the
   full suite must stay green and under the 2-minute budget. The eval suite (spec
   49) must remain deterministic and passing.
6. **Verify.** Run the full suite. Check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Write the changelog (applied vs. deliberately skipped)
   and any ADRs under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 51.

## One-line goal

The full agent feature (core + tools + diffs + streaming + chat UI + diff review
+ context parsing + safety) is hardened: bugs and prompt-injection holes fixed,
cost traps closed, UX rough edges smoothed, and test gaps filled — with no
behaviour regressions and no new features.

## Do NOT (scope guard)

- Do not add new agent capabilities, tools, UI screens, or config.
- Do not weaken any safety invariant: no auto-apply of diffs, untrusted-content
  framing intact, rate limits/budgets enforced, audit logging preserved.
- Do not change the diff format (43), streaming protocol (44), or apply flow (47)
  except to fix an outright bug (record it).
- Do not call a real LLM or external network in any test.
- Do not copy Overleaf source code (there is no agent equivalent).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
