# Spec 05 — Refactor Foundations

**Type:** 🔧 refactor  ·  **Phase:** Phase 0 — Foundations  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. This is a
**refactoring spec — it adds no features.** Do this:

1. **Read the requirements.** The full, authoritative process and acceptance
   criteria are in [`spec.md`](spec.md) next to this file. Follow the process
   exactly; the deliverable is *judgement-applied cleanup*, not new behaviour.
2. **Confirm prerequisites.** This spec depends on: **01, 02, 03, 04**. All must
   be implemented and their tests green before you begin. If the suite is red,
   stop — fix-to-green is the precondition, not part of this refactor.
3. **Study the Overleaf reference (for understanding only).** None for this spec
   — it is a process pass over Inkstave's own foundations. (Overleaf remains a
   read-only textbook under the originality rule, but no specific paths apply.)
4. **Run the analysis pass** described in `spec.md`: spawn analysis across specs
   01–04's output to find bugs, code smells, dead code, missing tests, and
   performance/security issues. For **each** finding, evaluate **risk vs.
   value** and decide apply-or-skip.
5. **Apply only the worthwhile fixes**, keeping all tests green at every step.
   Make small, reviewable commits. **No behaviour changes** to public contracts
   (endpoints, error envelope, settings names) unless the spec explicitly allows
   it and it is recorded.
6. **Verify.** The full suite must stay green and **under the 2-minute budget**.
7. **Record decisions.** Produce a changelog of applied vs. deliberately skipped
   findings under `docs/` (see §5/§8). This record is a required deliverable.

When all Definition-of-Done items pass, this spec is complete. Move to spec 06.

## One-line goal

After this spec the foundation code (01–04) is measurably cleaner — known bugs,
smells, dead code, and missing-test gaps triaged and the worthwhile ones fixed —
with **no behaviour change**, the suite still green and under budget, and a
documented record of what was changed and what was intentionally left.

## Do NOT (scope guard)

- Do not add new features or new endpoints; this is cleanup only.
- Do not change public contracts (API paths, error envelope shape, settings/env
  names, DB constraint names) unless `spec.md` explicitly permits and you record
  it as a deliberate, justified change.
- Do not rewrite working subsystems wholesale; prefer small, safe, reversible
  edits.
- Do not let the suite go red or exceed the 2-minute budget at any commit.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
