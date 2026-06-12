# Spec 35 — Refactor: collaboration

**Type:** 🔧 refactor  ·  **Phase:** Real-time collaboration  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. This is a
**refactoring spec** (every 5th): it adds **no new features**. Do this:

1. **Read the requirements.** The full, authoritative requirements are in
   [`spec.md`](spec.md) next to this file. Follow its scan → evaluate → apply →
   keep-green → changelog process exactly.
2. **Confirm prerequisites.** This spec depends on **31, 32, 33, 34** (the entire
   Phase-4 collaboration frontend, presence, sharing and access-control surface)
   being implemented with passing tests. It also implicitly touches the spec 28/29
   server CRDT/WS layer where the frontend and authz meet it.
3. **Study the Overleaf reference:** none for this spec. Refactoring is driven by
   Inkstave's own code, the earlier specs' acceptance criteria, and the rules in
   `CLAUDE.md`. (You still must not introduce Overleaf code.)
4. **Scan** the collaboration code (frontend Yjs binding + presence, sharing
   backend/UI, authorization) for bugs, permission holes, awareness/presence
   leaks, races, missing tests, and smells. **Evaluate** each finding (risk vs.
   value). **Apply** only the worthwhile fixes. Record what you changed and what
   you deliberately skipped.
5. **Keep everything green** and within the 2-minute test budget. Add tests that
   close real gaps you found.
6. **Verify** against the Definition of Done.

When all Definition-of-Done items pass, this spec is complete. Move to spec 36.

## One-line goal

The Phase-4 collaboration surface (live binding, presence, sharing, access
control) is measurably more correct, secure and maintainable — with no new
features, no behavioural regressions, and a recorded changelog of what was fixed
and what was intentionally left.

## Do NOT (scope guard)

- Do not add new features or new surfaces. Bug fixes, hardening, test gaps,
  dead-code removal and clarity refactors only.
- Do not change the approved stack or the spec 28/29 wire protocol semantics.
- Do not copy Overleaf source code.
- Do not make changes that drop test coverage or push the suite over 2 minutes.
- Do not silently change behaviour the earlier specs' acceptance criteria
  guarantee; if a criterion was wrong, fix it and note it explicitly in the
  changelog.
