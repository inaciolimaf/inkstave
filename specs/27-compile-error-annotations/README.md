# Spec 27 — Compile error & warning annotations

**Type:** 🟢 feature  ·  **Phase:** Compilation  ·  **Status:** ☑ done

## Prompt for the implementing agent

You are implementing **one** spec of the Inkstave system, in sequence. Do this:

1. **Read the requirements.** The full, authoritative requirements for this spec
   are in [`spec.md`](spec.md) next to this file. Implement *exactly* what it
   describes — no more, no less. If something is ambiguous, prefer the simplest
   option consistent with `CLAUDE.md` and stop to ask rather than invent scope.
2. **Confirm prerequisites.** This spec depends on: **24** (PDF preview UI +
   log panel — where the structured problems list is shown) and **18** (the
   CodeMirror 6 editor — where inline diagnostics are rendered). They must
   already be implemented and their tests passing. (Spec 24 itself depends on
   23/output storage, so the raw `output.log` is already retrievable.)
3. **Study the Overleaf reference (for understanding only).** Read the paths in
   the "Overleaf reference" section of `spec.md` inside `../overleaf/`. **Do not
   copy or translate any Overleaf code** — it is AGPLv3 and Inkstave is MIT.
   Learn how the LaTeX log is tokenised into errors/warnings/typesetting issues,
   then write your own parser.
4. **Implement** the backend log parser + endpoint and the frontend problems
   panel + CodeMirror diagnostics described in `spec.md`.
5. **Write the tests** listed in the spec's Test plan (unit / integration / e2e).
6. **Verify.** Run the full test suite. It must pass and the whole suite must
   stay under the 2-minute budget. Then check every Acceptance criterion and
   Definition-of-Done item.
7. **Record decisions.** If you made an architectural decision (parser strategy,
   severity mapping), add a short note under `docs/`.

When all Definition-of-Done items pass, this spec is complete. Move to spec 28.

## One-line goal

After a compile, the user sees a structured list of errors and warnings (with
file, line, severity and message) in a problems panel and as inline markers at
the right lines in the editor.

## Do NOT (scope guard)

- Do not implement SyncTeX source↔PDF click sync — that is spec 26.
- Do not run compiles or change output storage; reuse specs 21–24.
- Do not copy Overleaf's log parser (`latex-log-parser.ts`) — study only.
- Do not introduce technologies outside the approved stack (`CLAUDE.md`).
