# Spec 74 — Fix-pack: collaboration, editor settings & agent-scope cleanups

**Type:** 🩹 fix-pack · **Phase:** validation remediation · **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec — it is a curated bundle of **confirmed issues** found by a
validation pass (two independent reviewers agreed each is real). Do this:

1. **Read the requirements.** The authoritative, per-issue requirements are in
   [`spec.md`](spec.md) next to this file. Apply **exactly** the fixes it lists —
   no more, no less. Each issue cites the source spec, the file(s), the problem,
   and the concrete fix to apply.
2. **Stay inside the file set.** This fix-pack was selected so its files are
   **disjoint** from every other parallel fix-pack (so packs can run in
   parallel safely). **Do NOT touch any file outside the "Files in scope" list
   in `spec.md`.** If a fix seems to need an out-of-scope file, stop and flag it
   rather than editing it.
3. **No unrelated refactors.** Fix only what each issue describes. Do not rename,
   re-architect, or "improve" neighbouring code.
4. **Follow `CLAUDE.md`.** Match existing style, conventions, and the approved
   stack. Async-first backend; strict-mode TypeScript frontend.
5. **Tests stay green and fast.** After your changes, run the full suite. It must
   pass and the whole suite must stay **under 2 minutes**. Add the new/updated
   tests this fix-pack requires; do not let any test introduce real wall-clock
   waits.

When every Acceptance criterion and Definition-of-Done item in `spec.md` passes,
this fix-pack is complete.

## One-line goal

Close the confirmed collaboration/editor/agent-scope gaps (live CRDT convergence
test, deterministic reconnect test, undo-scoping & throttle-integration tests,
the missing keymap selector in the editor settings popover, a duplicated
constant, and two documentation/scope notes) without touching any other pack's
files.

## Do NOT (scope guard)

- Do not edit files outside the "Files in scope" list in `spec.md`.
- Do not implement features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
- Do not add tests that wait on real timers; use fake timers.
