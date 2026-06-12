# Spec 75 — Fix-pack: diff-review UI hardening, auth & contract alignment

**Type:** 🩹 fix-pack · **Phase:** validation remediation · **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one fix-pack** of the Inkstave system. This is **not** a
feature spec — it is a curated bundle of **confirmed issues** found by a
validation pass (two independent reviewers agreed each is real). Do this:

1. **Read the requirements.** The authoritative, per-issue requirements are in
   [`spec.md`](spec.md) next to this file. Apply **exactly** the fixes it lists —
   no more, no less.
2. **Stay inside the file set.** This fix-pack was selected so its files are
   **disjoint** from every other parallel fix-pack (parallel-safe). **Do NOT
   touch any file outside the "Files in scope" list in `spec.md`.** If a fix
   seems to need an out-of-scope file, stop and flag it rather than editing it.
3. **The MAJOR diff-review UI fixes are the priority.** Three confirmed MAJOR
   issues harden the diff-review surface: confirm-before-discard on accidental
   dismiss, replace the raw `<pre>` preview with a read-only CodeMirror, and
   render a distinct apply-error state (and stop the false success toast). Make
   these correct and tested.
4. **No unrelated refactors.** Fix only what each issue describes.
5. **Follow `CLAUDE.md`.** Match existing style and the approved stack
   (CodeMirror 6, shadcn/ui, React + strict TS; async-first backend).
6. **Tests stay green and fast.** Run the full suite after your changes; it must
   pass and stay **under 2 minutes**. Add the new/updated tests this fix-pack
   requires (including an accept-all / reject-all test and an apply-error test).

When every Acceptance criterion and Definition-of-Done item in `spec.md` passes,
this fix-pack is complete.

## One-line goal

Harden the diff-review dialog (discard guard, CodeMirror preview, error state,
spec-faithful types/labels) and align a handful of backend/doc interface
contracts — without touching any other pack's files.

## Do NOT (scope guard)

- Do not edit files outside the "Files in scope" list in `spec.md`.
- Do not implement features that belong to later specs.
- Do not copy Overleaf source code.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`); reuse
  the existing read-only CodeMirror configuration rather than a new editor lib.
