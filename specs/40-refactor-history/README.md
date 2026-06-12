# Spec 40 — Refactor: History & Notifications

**Type:** 🔧 refactor  ·  **Phase:** Phase 5 — Version history  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing a **refactoring** spec. It adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md). This spec scans everything built in Phase 5 (specs 36–39:
   history capture, history API, history UI, notifications & email) for bugs,
   storage bloat, restore-correctness issues, email-job reliability problems, and
   missing tests; evaluates each finding (risk vs. value); applies the worthwhile
   fixes; keeps the suite green and under 2 minutes; and records a changelog.
2. **Confirm prerequisites.** Depends on **36, 37, 38, 39** — all implemented with
   passing tests.
3. **No Overleaf reference.** This spec has none — it works only on Inkstave's own
   code. Do not copy Overleaf code (the originality rule still applies).
4. **Find → evaluate → apply.** For each candidate fix, judge whether it is worth
   the risk; apply only the worthwhile ones. Skipped findings are recorded with a
   reason. Never destroy restorable history; never weaken access control.
5. **Keep tests green.** Add tests for any bug you fix and any gap you find; the
   full suite must stay green and under the 2-minute budget.
6. **Verify.** Run the full suite. Check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** Write the changelog (applied vs. deliberately skipped) and
   any ADRs under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 41.

## One-line goal

Phase 5 (history + notifications) is hardened: known bugs fixed, storage bloat and
restore correctness addressed, email jobs made reliable, and test gaps closed —
with no behaviour regressions and no new features.

## Do NOT (scope guard)

- Do not add new features or new user-facing capabilities.
- Do not change public API/route contracts unless fixing an outright bug (record it).
- Do not reduce the set of restorable history versions or weaken authz.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
