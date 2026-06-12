# Spec 25 — Refactor: Compilation

**Type:** 🔧 refactor  ·  **Phase:** Compilation  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing a **refactoring** spec of the Inkstave system. It adds **no
new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md) next to this file. Implement *exactly* what it describes.
2. **Confirm prerequisites.** This spec depends on **21, 22, 23, 24** being fully
   implemented with their tests passing. The whole suite must be green before you
   start, so you can tell what your changes break.
3. **Scan, evaluate, fix.** Systematically scan the compilation code (service,
   ARQ jobs, output storage, preview UI) for the problem classes listed in
   `spec.md` — bugs, resource leaks, temp-dir cleanup gaps, timeout/cancellation
   correctness, security-model gaps, missing tests, and especially **test-speed
   regressions** (any real Tectonic compile that leaked into a fast tier). For
   each finding, **judge whether the fix is worth it** (risk vs. value) and apply
   only the worthwhile ones.
4. **Keep green.** All existing tests must stay passing; add tests for the bugs
   you fix and the speed-guards you add.
5. **Verify the budget.** Re-measure: the full suite must run in **< 2 minutes**
   and the fast tiers must contain **zero real compiles**.
6. **Changelog.** Record what you changed and what you deliberately skipped (and
   why) — see §"Deliverables" in `spec.md`.

There is **no Overleaf reference** for this spec.

When all Definition-of-Done items pass, this spec is complete. Move to spec 26.

## One-line goal

The compilation subsystem (specs 21–24) is measurably more correct, leak-free,
and fast-to-test after a deliberate, documented refactor pass — with no behaviour
regressions and no new features.

## Do NOT (scope guard)

- Do not add new features or new endpoints; this is a cleanup pass.
- Do not pull work forward from specs 26/27 (synctex, log annotations).
- Do not let any real Tectonic compile run in the unit or integration tiers.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
