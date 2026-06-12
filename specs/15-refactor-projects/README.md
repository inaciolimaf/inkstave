# Spec 15 — Refactor pass over projects & files

**Type:** 🔧 refactor  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. This is a
**refactoring** spec: it adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative process and acceptance
   criteria are in [`spec.md`](spec.md) next to this file.
2. **Confirm prerequisites.** This spec depends on **11, 12, 13, 14** being fully
   implemented with green tests.
3. **No Overleaf reference.** There is nothing to copy or study here; this is an
   inward pass over Inkstave's own code.
4. **Scan, evaluate, apply.** Systematically review everything built in specs
   11–14 for bugs, smells, N+1 queries, missing indexes, path-safety holes, and
   missing tests. For each finding, judge risk vs. value and apply only the
   worthwhile fixes. Keep all tests green throughout.
5. **No behaviour change.** External API contracts and observable behaviour must
   stay identical (except fixing outright bugs, which must be covered by a new
   regression test). Do not add features or scope.
6. **Verify.** Full suite green and under the 2-minute budget. Produce a changelog
   of what was changed and what was deliberately skipped (with reasons).

When all Definition-of-Done items pass, this spec is complete. Move to spec 16.

## One-line goal

The projects-and-files backend (specs 11–14) is cleaner, faster and better-tested
after this pass, with no change to its external behaviour beyond bug fixes that
carry their own regression tests.

## Do NOT (scope guard)

- Do not add new features or endpoints.
- Do not change API contracts or response shapes (except to fix a documented bug,
  with a regression test).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not copy Overleaf source code.
