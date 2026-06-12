# Spec 26 — SyncTeX source ↔ PDF synchronisation

**Type:** 🟢 feature  ·  **Phase:** Compilation  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **23** (output storage —
   provides the stored `.synctex.gz`, PDF and log artefacts for a compile) and
   **24** (PDF preview UI — provides the PDF.js viewer and the open editor this
   spec wires sync into). They must already be implemented and their tests
   passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the approach (especially how `synctex view`/`edit`
   output is parsed and how the viewer highlights are positioned), then write
   your own implementation.
4. **Implement** the backend SyncTeX parser + endpoints and the frontend
   click-to-sync wiring described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (e.g. parsing the
   `.synctex.gz` directly vs. shelling out to the `synctex` binary), add a short
   note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 27.

## One-line goal

A user can click anywhere in the PDF preview to jump to the matching source line
in the editor, and click in the editor to highlight the matching region in the
PDF.

## Do NOT (scope guard)

- Do not implement compile-error/warning annotations — that is spec 27.
- Do not re-implement compilation, output storage or the PDF viewer; reuse specs
  21–24.
- Do not copy Overleaf source code (its `SynctexOutputParser.js` is study-only).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
