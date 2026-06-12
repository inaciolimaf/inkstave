# Spec 24 — PDF Preview UI (PDF.js)

**Type:** 🟢 feature  ·  **Phase:** Compilation  ·  **Status:** ☐ not started

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **18** (the CodeMirror editor
   UI shell and editor layout) and **23** (output storage: the PDF and log
   endpoints), plus the compile API of **22**. They must already be implemented
   and their tests passing.
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside the cloned repo at
   `../overleaf/`. **Do not copy or translate any Overleaf code** — it is AGPLv3
   and Inkstave is MIT. Learn the UI approach (compile button, preview pane, log
   panel), then write your own React/PDF.js implementation.
4. **Implement** the PDF preview pane: a Compile button (spec 22), compiling
   state, PDF.js rendering of the result (spec 23) with zoom/page nav, and a
   collapsible raw-log panel, plus a clear error state.
5. **Write the tests** listed in the spec's Test plan. **All network calls are
   mocked** (no real backend compile); PDF.js is exercised against a tiny fixture
   PDF or mocked.
6. **Verify.** Run the full test suite under the 2-minute budget; check every
   Acceptance criterion and Definition-of-Done item.
7. **Record decisions.** Add a short note under `docs/` if you make a PDF.js
   worker/bundling decision worth recording.

When all Definition-of-Done items pass, this spec is complete. Move to spec 25.

## One-line goal

A user can click Compile, watch the compile run, and see the resulting PDF
rendered with zoom and page navigation alongside a collapsible raw compile-log
panel — with a clear error state when the compile fails.

## Do NOT (scope guard)

- Do not implement clickable SyncTeX (source↔PDF jump) — that is spec 26.
- Do not parse the log into inline editor annotations — that is spec 27.
- Do not re-implement the compile API or output storage — call specs 22/23.
- Do not copy Overleaf source code (the frontend is AGPLv3).
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
