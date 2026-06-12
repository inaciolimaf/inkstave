# Spec 18 — Editor UI (CodeMirror 6)

**Type:** 🟢 feature  ·  **Phase:** Projects & files  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **17** (file tree UI, which
   emits the selected document) and **13** (document content API, which serves
   document text + version). They must already be implemented and tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. In particular **do NOT copy the `lezer-latex` grammar**;
   use an independently-licensed (MIT/permissive) LaTeX language package instead.
4. **Implement** the CodeMirror 6 editor pane and the 3-pane IDE shell.
5. **Write the tests** listed in the spec's Test plan.
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (which LaTeX
   language package, licensing), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 19.

## One-line goal

Selecting a document in the file tree opens it in a CodeMirror 6 pane with LaTeX
syntax highlighting, line numbers and basic settings — read-only at this stage.

## Do NOT (scope guard)

- Do not implement editing persistence / autosave — this baseline is **read-only**
  (typing is disabled or discarded); saving arrives in spec 19.
- Do not implement collaboration (Yjs binding, cursors), compile, or PDF preview
  — the preview pane is a **placeholder** here.
- Do not copy Overleaf's `lezer-latex` grammar or any Overleaf source. Use a
  permissively-licensed CM6 LaTeX language package.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
