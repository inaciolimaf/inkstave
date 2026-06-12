# Spec 20 — Refactor: Editor & File-Tree UI

**Type:** 🔧 refactor  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing a **refactoring** spec of the Inkstave system, in sequence.
Refactoring specs add **no new features**. Do this:

1. **Read the requirements.** The full, authoritative process for this spec is in
   [`spec.md`](spec.md) next to this file. Follow it exactly.
2. **Confirm prerequisites.** This spec depends on **16, 17, 18, 19** (the
   project dashboard, file tree, CodeMirror editor and REST autosave) being
   implemented with their tests green. Run the suite first to confirm a green
   baseline before changing anything.
3. **No Overleaf reference for this spec.** There is nothing to study; this is an
   inward-looking quality pass. Still obey the originality rule: never introduce
   copied Overleaf code while refactoring.
4. **Scan, evaluate, apply.** Scan the editor + file-tree + dashboard UI for
   bugs, accessibility issues, re-render/performance problems, dead code and
   missing tests. For each finding, judge risk vs. value and apply only the
   worthwhile fixes, keeping all tests green.
5. **Keep behavior the same.** Refactors must not change user-visible behavior or
   scope (no features from later specs). If a fix changes behavior, it must be a
   genuine bug fix with a test proving the correction.
6. **Verify.** The full suite must pass and stay under the 2-minute budget after
   every change. Add tests for any bug you fix and any gap you close.
7. **Record decisions.** Produce a changelog of what was changed and what was
   deliberately skipped (with reasons), under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 21.

## One-line goal

The Phase-2 frontend (dashboard, file tree, editor, autosave) is cleaner, more
accessible, faster to re-render and better tested — with no behavior or scope
changes — and the decisions are recorded.

## Do NOT (scope guard)

- Do not add features or pull in functionality from later specs.
- Do not change public API contracts (specs 11–14) or user-visible behavior
  except as a tested bug fix.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not break the < 2-minute test budget.
